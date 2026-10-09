"""Summarizer qualification tooling for `calculator-constraints-v1` (Plan 12.2 Task 8).

Design spec 6.5-6.6 and Task 1 contracts 3. Only `run` makes paid calls. This module provides:

- `evaluate_summary`: a deterministic fact report. It checks the `context-summary-v1` format, a
  complete (`stop`) finish, every required fact, the current and superseded rounding rules, and no
  invented approval, deletion or reversed correction. With a reading of the scenario by Claude and
  Codex, it is a limited gate, not a statistical guarantee of model quality.
- `run_qualification`: the two-step run against an injected summarizer. Step 1 summarizes the early
  turns; step 2 merges that summary with the turns holding the correction. It makes at most two
  calls, checks a dollar cap before each, never retries until a pass, and yields receipt fields only
  for a pass.
- `paid_envelope`: what the operator approves before any paid call. Per assigned summarizer it gives
  structural blockers other than the missing receipt, exact input/output caps, the attempt ceiling and
  the cost reservation.
- `run_live`: the paid qualification of the reviewed `qualification` test profile (Plan 12.2 Stage B;
  Codex Haiku Stage A review, launcher ruling). A client of the Gateway that the operator-started,
  profiled host owns: it never starts a Gateway or contacts a provider itself, and the Gateway's own
  binding check refuses any other snapshot before a provider attempt. No other model client may use
  that Gateway during the run: its route stop is not a concurrent admission barrier.

Usage:
    python tools/evaluate_context_summarizer.py envelope [--registry FILE] [--override FILE]
    python tools/evaluate_context_summarizer.py check --summary FILE --step {step1,final} [--finish-status stop]
    python tools/evaluate_context_summarizer.py run --profile qualification --host-pid PID --gateway-pid PID --out NEW_DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from importlib import resources
from pathlib import Path
from types import MappingProxyType
from typing import Any

from context_engine import MaintenanceRequest, OrdinaryTurn
from context_engine.engine import maintenance_input
from context_engine.summary import (
    PROMPT_DIGEST,
    PROMPT_VERSION,
    SECTIONS,
    SUMMARY_FORMAT,
    VALIDATOR_VERSION,
    SummaryFormatError,
    build_summary_prompt,
    parse_summary,
)
from optimus.acp.conversation import ConversationSanitizer, ConversationSanitizerInputs
from optimus.acp.local_gateway_secrets import resolve_shared_secret
from optimus.acp.operator_paths import resolve_config_root
from optimus.config.gateway import OptimusGatewaySettings
from optimus.context.maintenance import (
    HostMaintenance,
    MaintenanceIdentity,
    MaintenanceReceipt,
    SummarizerCall,
    SummarizerResponse,
    SummarizerRoute,
    gateway_summarizer_factory,
)
from optimus.gateway.client import GatewayClient
from optimus_model_policy import RegistrySnapshot, Role, load_registry, ordered_assignments, validate_registry
from optimus_model_policy.binding import MAX_ROUTE_ATTEMPTS, disclosure_key
from optimus_model_policy.experimental import EMPIRICAL_ESTIMATOR_METHOD, experimental_route
from optimus_model_policy.registry import SummaryReceipt
from optimus_model_policy.test_profiles import compose_test_profile_snapshot

# v2 is v1 with the runtime summary output allocation, 8,192 tokens (ADR-018), in place of v1's
# 1,200-token test cap. v1 stays as the fixture of Stage B run 1 (Codex Stage B v2 disposition).
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "context_engine" / "calculator-constraints-v2.json"
MAX_FIXTURE_CALLS = 2
# A summary's runtime byte bound, floor(S / r) (ADR-018): 8,192 UTF-8 bytes for the qualification
# profile's S = 8,192 tokens and empirical r = 1 token per byte. A separate limit from the output
# allocation, which does not bound a summary's bytes. The step 1 summary is checked before it is
# carried into step 2 (over it, step 2 is unrun) and the final summary before any receipt (over it, the
# run is not a pass); neither is ever truncated.
SUMMARY_MAX_BYTES = 8192
_MILLION = Decimal(1_000_000)
# Sentences end at . ! or ? followed by whitespace, or at a newline. A decimal point is not an end;
# a semicolon joins clauses that belong together ("ROUND_HALF_UP; now ROUND_HALF_EVEN"), so the
# supersession check reads whole sentences. Facts and claims are read per clause: a sentence split
# again at its semicolons, so one clause's negation never reaches another clause's claim.
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n")
_CLAUSE = ";"
# A negation carries over a coordinated claim: "not approved or granted".
_COORDINATED = re.compile(r"\s*,?\s*(?:or|nor)\s*")


@dataclass(frozen=True, slots=True)
class FactRules:
    """The fixture's lexical rules, shared by both steps. They are fixture data, so the fixture
    digest that every receipt binds covers them."""

    negation: str  # governs the next fact or claim match (anchored at it with `$`)
    reported: str  # reported speech governs a forbidden claim: "told the agent to record every plan as approved"
    markers: tuple[str, ...]  # supersession markers no negation reverses: "previously", "no longer", "anymore"
    verbs: tuple[str, ...]  # supersession verbs an adjacent negation reverses: "was not superseded"
    verb_negation: str
    forbidden: tuple[Mapping[str, str], ...]


@dataclass(frozen=True, slots=True)
class Fixture:
    name: str
    digest: str
    turns: Mapping[int, OrdinaryTurn]
    step1: tuple[int, ...]
    step2: tuple[int, ...]
    tail: tuple[int, ...]
    max_output_tokens: int
    step1_facts: tuple[Mapping[str, Any], ...]
    final_facts: tuple[Mapping[str, Any], ...]
    rules: FactRules
    history: SourceHistory


# Validator v5 (Codex historical-checker review, 2026-10-09). An otherwise unaccounted mention of a superseded rule
# is excused only as a dated record of a creation event the fixture's own source records as completed
# before its correction, written in the Work and evidence or Source chronology section as
# "Seq N: [The source records that] Created <artifact> <payload>" or "... <artifact> was created
# <payload>", matching the source event exactly. A limited lexical contract, not a paraphrase reader.
_HISTORY_SECTIONS = frozenset({"Work and evidence", "Source chronology"})
_DATED = re.compile(r"(?:[-*]\s+)?seq\s+(\d+):\s+(?:the source records that\s+)?(.+)")
_ACTIVE_CREATION = re.compile(r"created\s+(\S+)\s+(.+)")
_PASSIVE_CREATION = re.compile(r"(\S+)\s+was created\s+(.+)")
# An affirmative current use of a superseded rule (an instruction, a requirement or a present use) fails
# whatever marker, record or replacement stands beside it (Codex validator v5 batch review, M5). A bounded
# lexical grammar, not a parser, in three shapes:
# - the rule as an object: a use, keep, select or reinstating verb, a continuation ("keep using", "continue
#   with", "still apply"), a rounding verb, active or passive ("round amounts with", "totals are quantized
#   using"), or a switch ("switch to", "set the rounding mode to") before a noun phrase naming the rule
#   ("the original ROUND_HALF_UP", "the rounding mode ROUND_HALF_UP", "decimal.ROUND_HALF_UP");
# - the rule as a subject: a present or modal requirement ("is still being used", "must be applied", "can
#   still be used", "still applies", "remains", "remains the default", "is the rule to use");
# - the rule as the rounding mode a clause states ("the rounding mode is still ROUND_HALF_UP", "rounding
#   must be ROUND_HALF_UP").
# A local negation governs a match it precedes ("do not keep using ..."), as it governs every other claim,
# and so does a contrast ("ROUND_HALF_EVEN rather than ROUND_HALF_UP applies"). Only the listed adverbs may
# stand inside a predicate, so a negated predicate never matches ("must not be used", "is no longer the
# rounding mode"). The patterns are code, so the validator version covers them; `{rule}` is the rule.
_ADVERBS = r"(?:(?:still|now|also|again|always|currently)\s+)*"
_STALE = r"(?:original|old|older|previous|prior|earlier|initial|former|superseded|legacy|same|existing)"
_CURRENT = r"(?:current|active|default|required|correct|right|only|live|governing|applicable)"
_MODE = r"(?:rounding\s+(?:mode|rule|method|setting)|rounding|mode|rule|method|setting|default|choice|one)"
_RULE_NP = (
    r"(?:(?:the|a|an|that|this|its)\s+)?(?:" + _STALE + r"\s+)*(?:(?:rounding\s+)?(?:mode|rule|method|setting)\s+|rounding\s+)?"
    r"(?:rounding\s*=\s*)?[(`'\"]?(?:decimal\.)?{rule}\b"
)
_RULE_SUBJECT = r"\b{rule}[)`'\"]?(?:\s+(?:rounding(?:\s+(?:mode|rule|method|setting))?|mode|rule|method|setting))?\s+"
_MODAL = r"(?:must|should|shall|will|can|may|has\s+to|have\s+to|needs?\s+to|is\s+to|are\s+to)"
_PRESENT_USE = (
    r"(?:being\s+)?(?:used|applied|kept|retained|enforced|required|mandatory|needed|necessary|preferred|allowed|permitted|valid|unchanged"
    r"|current|active|(?:the\s+)?default|in\s+(?:effect|use|force|place))\b"
)
_ROUND_VERB = r"(?:round|rounds|quanti[sz]e|quanti[sz]es)"
_WITHDRAW = r"(?:drop|remove|replace|change|abandon|retire|discard|deprecate|override|supersede|stop\s+using|stop\s+applying)"
_WITHDRAWN = r"(?:dropped|removed|replaced|changed|abandoned|retired|discarded|deprecated|overridden|superseded|superceded)"
# A rounding verb's object, precision and preposition: "amounts to 0.01 with", "to 2 decimal places using".
_ROUND_COMPLEMENT = (
    r"(?:(?:all|every|each|the|new|future)\s+)?(?:(?:amounts?|values?|results?|numbers?|totals?|calculations?|outputs?|sums?)\s+)?"
    r"(?:to\s+[\w.]+(?:\s+(?:decimal\s+)?places?)?\s+)?(?:with|using|by|via|per|under)\s+"
)
# The rule as an object.
_USE_OBJECT = (
    r"\b(?:use|uses|apply|applies|keep|keeps|retain|retains|require|requires|adopt|adopts|reinstate|reinstates|restore|restores"
    r"|implement|implements|employ|employs|enforce|enforces|prefer|prefers|choose|chooses|select|selects|enable|enables)\s+" + _RULE_NP,
    r"\b(?:keep|keeps|keeping|continue|continues|continuing|still|now|resume|resumes|go on|goes on|carry on|carries on)\s+(?:to\s+)?"
    r"(?:(?:use|using|apply|applying)\s+|(?:" + _ROUND_VERB + r"|rounding|quanti[sz]ing)\s+" + _ROUND_COMPLEMENT + r")" + _RULE_NP,
    r"\b(?:continue|continues|continuing|stick|sticks|sticking|stay|stays|staying|go|goes|carry on|carries on|proceed|proceeds)\s+with\s+" + _RULE_NP,
    r"\b" + _ROUND_VERB + r"\s+" + _ROUND_COMPLEMENT + _RULE_NP,
    r"\b(?:is|are|gets?|" + _MODAL + r"\s+be)\s+" + _ADVERBS + r"(?:being\s+)?(?:rounded|quanti[sz]ed|done|performed|handled|computed)\s+"
    + _ROUND_COMPLEMENT + _RULE_NP,
    r"\b(?:switch|switches|change|changes|move|moves|return|returns|revert|reverts|go|goes|default|defaults)\s+(?:back\s+)?to\s+" + _RULE_NP,
    r"\b(?:set|sets)\s+(?:the\s+)?(?:rounding(?:\s+(?:mode|rule|method|setting))?|mode|rule|it)\s+(?:back\s+)?to\s+" + _RULE_NP,
    r"\b(?:stick|sticks|keep|keeps|hold|holds|adhere|adheres)\s+to\s+" + _RULE_NP,
    r"\b(?:rely|relies|depend|depends)\s+on\s+" + _RULE_NP,
    r"\b(?:leave|leaves)\s+" + _RULE_NP + r"\s+(?:in\s+place|as\s+is|unchanged|alone|untouched)\b",
)
_CURRENT_USE = (
    *_USE_OBJECT,
    # An instruction not to withdraw the rule keeps it: the negation is part of the claim.
    r"\b(?:do\s+not|don't|never|must\s+not|mustn't|should\s+not|shouldn't)\s+" + _WITHDRAW + r"\s+" + _RULE_NP,
    # The rule as a subject.
    _RULE_SUBJECT + r"(?:is|are|remains|stays)\s+" + _ADVERBS + _PRESENT_USE,
    _RULE_SUBJECT + _MODAL + r"\s+" + _ADVERBS + r"(?:be|remain|stay)\s+" + _ADVERBS + _PRESENT_USE,
    _RULE_SUBJECT + r"(?:" + _MODAL + r"\s+" + _ADVERBS + r"(?:remain|stay)|remains|stays)(?=\s*(?:[.;,!?)]|$))",
    _RULE_SUBJECT + _ADVERBS + r"(?:applies|governs)\b",
    _RULE_SUBJECT + _MODAL + r"\s+" + _ADVERBS + r"(?:apply|govern)\b",
    # A withdrawal of the rule required not to happen, or denied: "must not be replaced", "was not superseded"
    # (but not "was not replaced until seq 7", which dates the withdrawal).
    _RULE_SUBJECT + r"(?:" + _MODAL + r"\s+(?:not|never)|mustn't|shouldn't|can't|cannot|won't)\s+be\s+" + _WITHDRAWN + r"\b",
    _RULE_SUBJECT + r"(?:(?:is|was|has|have)\s+(?:not|never)|isn't|wasn't|hasn't|haven't)\s+(?:been\s+)?" + _WITHDRAWN
    + r"\b(?!\s+(?:until|till|before)\b)",
    _RULE_SUBJECT + r"(?:(?:remains|stays)\s+" + _ADVERBS + r"|is\s+(?:(?:still|now|also|again|currently)\s+)+)the\s+(?:" + _CURRENT + r"\s+)?" + _MODE + r"\b",
    _RULE_SUBJECT + r"is\s+the\s+" + _CURRENT + r"\s+" + _MODE + r"\b",
    _RULE_SUBJECT + r"is\s+the\s+" + _MODE + r"\s+(?:to\s+(?:use|apply|follow)|in\s+(?:effect|use|force|place)|now|going\s+forward|from\s+now\s+on)\b",
    # The rule as the rounding mode a clause states.
    r"(?:^|[;:,(]|\b(?:and|but|so|yet|while)\b)\s*(?:[-*]\s+)?(?:the\s+)?(?:" + _CURRENT + r"\s+)?"
    r"(?:rounding(?:\s+(?:mode|rule|method|setting))?|mode|rule|method|setting)\s+"
    r"(?:is|remains|stays|" + _MODAL + r"\s+" + _ADVERBS + r"(?:be|remain|stay))\s+" + _ADVERBS + _RULE_NP,
)
# A contrast right before a current use governs it: the old rule is what the clause does not use.
_CONTRAST = r"\b(?:instead of|rather than|replacing|superseding|overriding)\s+(?:(?:the|a|an|that|this|its)\s+|" + _STALE + r"\s+)*$"

# Occurrence accounting (Codex M5 review of a04e33b, 2026-10-09). A sentence-wide marker no longer accepts an
# unrecognized claim: every occurrence of the superseded rule must lie inside a supported non-current construction
# that spans its whole claim, from a clause start to a clause end, or inside an exact dated source record.
# Anything else fails as unsupported, current or not. The constructions are a bounded grammar in code: free text
# inside them never holds the rule, a negation or a joining word, and their withdrawal verbs are the fixture's own
# (`{wd}`). Whether an accounted statement states the supersession is still decided by the fixture's markers and
# verbs, inside that statement.
_NEGATING = r"\b(?:not|never|no|nor|neither|none|nothing|nobody|cannot|without|avoid\w*|stop\w*|refus\w*|fail\w*|forg[eo]t\w*)\b|n't\b"
_JOINING = r"\b(?:and|or|but|yet|except|unless|although|though|while|whereas|however|which|who|if|whether|would|could|might)\b"
_CONTINUING = r"\b(?:still|currently|itself)\b"
_FREE = r"(?:(?!{rule}|" + _NEGATING + "|" + _JOINING + "|" + _CONTINUING + r")(?:[^.;:()\n,]|\.(?=\S)))+"
_WHEN = r"(?:later|since|then|now|already|also|subsequently|eventually|explicitly)"
_PREP = r"(?:by|with|to|in|at|for|from|on|after|during|per|under|until|till|before|as\s+of)"
_ADJUNCTS = r"(?:\s+(?:" + _WHEN + r"|anymore|everywhere|entirely|completely)\b)*(?:\s+" + _PREP + r"\s+" + _FREE + r")?"
_HEAD_NOUN = r"[)`'\"]?(?:\s+(?:rounding(?:\s+(?:mode|rule|method|setting))?|mode|rule|method|setting))?"
# A parenthetical label naming the rule's source or age: "(the seq 1 rule)", "(the original rule)".
_LABEL = r"(?:\s*\(\s*(?:the\s+)?(?:(?:seq|turn)\s+\d+|" + _STALE + r")(?:\s+(?:rounding\s+)?(?:rule|mode|one|constraint|setting))?\s*\))?"
_RULE_REF = _RULE_NP + _HEAD_NOUN + _LABEL
# The rule as a subject, with its source ("from seq 1", "(the seq 1 rule)") or an appositive ("ROUND_HALF_UP, the
# original rule,").
_RULE_HEAD = (
    r"(?:(?:rounding|quanti[sz]ing)\s+(?:with|using|by)\s+|(?:the\s+)?use\s+of\s+|using\s+|applying\s+)?" + _RULE_REF
    + r"(?:\s+(?:from|in|of)\s+(?:seq|turn)\s+\d+)?"
    + r"(?:\s*,\s*(?:the|its)\s+(?:" + _STALE + r"\s+)*(?:rounding\s+)?(?:rule|mode|one))?\s*,?"
)
_PASSIVE = r"(?:was|were|is|are|has\s+been|have\s+been|had\s+been|got|gets|(?:must|should|shall|will|can|may|is\s+to|are\s+to)\s+be)"
_NOT_NOW = r"(?:not|never|no\s+longer)"
_IN_USE = (
    r"(?:used|applied|kept|retained|allowed|permitted|required|needed|valid|current|active|(?:the\s+)?default"
    r"|in\s+(?:use|effect|force|place)|(?:the\s+)?(?:current\s+)?(?:rounding\s+(?:mode|rule)|rule|mode|one))"
)
_REINSTATED = r"(?:used|applied|kept|retained|allowed|reinstated|restored)"
# A non-current predicate of the rule: "is not used anymore", "must not be used", "no longer applies", "remains
# superseded", "is the old rule".
_NOT_IN_USE = (
    r"(?:(?:is|are|was|were)\s+" + _NOT_NOW + r"\s+(?:being\s+)?" + _IN_USE
    + r"|(?:isn't|aren't|wasn't|weren't)\s+(?:being\s+)?" + _IN_USE
    + r"|(?:must|should|shall|will|can|may)\s+" + _NOT_NOW + r"\s+be\s+" + _REINSTATED
    + r"|(?:mustn't|shouldn't|can't|cannot|won't)\s+be\s+" + _REINSTATED
    + r"|(?:no\s+longer|never)\s+(?:applies|apply|governs|holds)|(?:does\s+not|doesn't|did\s+not|didn't)\s+(?:apply|govern)"
    + r"|(?:remains|stays|(?:must|should)\s+(?:remain|stay))\s+{wd}"
    + r"|(?:is|was)\s+the\s+" + _STALE + r"\s+(?:rounding\s+)?(?:rule|mode|one|default|setting))"
)
_ROUNDED = r"(?:rounded|quanti[sz]ed|done|performed|handled|computed)"
_BY_USING = r"(?:using\s+|applying\s+|(?:rounding|quanti[sz]ing)\s+(?:with|using|by)\s+)?"
# Tails that complete a claim: a relative clause or a reason stating the withdrawal, then prepositional trailers.
_RELATIVE = (
    r"\s*,?\s*which\s+(?:" + _PASSIVE + r"\s+(?:" + _WHEN + r"\s+)?{wd}|(?:" + _FREE + r"\s+)?{wd}|(?:is|was)\s+no\s+longer\s+(?:used|applied))"
    + _ADJUNCTS
)
_REASON = (
    r"(?:\s*[:;]\s*|\s*,?\s*(?:since|because|as)\s+)(?:it|this)\s+" + _PASSIVE + r"\s+(?:" + _WHEN + r"\s+)?{wd}" + _ADJUNCTS
    + r"|\s*\(\s*(?:(?:it|this)\s+" + _PASSIVE + r"\s+)?(?:" + _WHEN + r"\s+)?{wd}" + _ADJUNCTS + r"\s*\)"
)
_ANAPHORIC = r"\s*[;,]\s*(?:" + _FREE + r"\s+)?(?=\w+(?:ed|es)\b){wd}\s+it\b" + _ADJUNCTS
_AND_NOT_IN_USE = r"\s*,?\s+and\s+" + _NOT_IN_USE + _ADJUNCTS
_TRAILERS = r"(?:\s*,\s*" + _PREP + r"\s+" + _FREE + r")*"
_TAIL = r"(?:" + _RELATIVE + "|" + _REASON + "|" + _AND_NOT_IN_USE + r")?" + _TRAILERS
# A claim ends at a closing parenthesis or the sentence end; at a semicolon, colon or opening parenthesis unless a
# pronoun, a description of the old rule, a conjunction or a predicate continues it; and at a comma or conjunction
# only before a new subject.
_OLD_RULE = r"(?:the|its)\s+" + _STALE + r"\s+(?:rounding\s+)?(?:rule|mode|one|setting)\b"
_CONTINUES = (
    r"(?:(?:it|this|that|they|these|those|still|also|and|but|yet|is|are|was|were|remains|stays|must|should|shall|will|can|may"
    r"|keeps|continues|applies|governs)\b|" + _OLD_RULE + r"|\w+\s+(?:it|this|that|them)\b)"
)
_NEW_SUBJECT = (
    r"(?!" + _OLD_RULE + r")(?:the|a|an|its|their|our|every|each|all|both|seq\s+\d+|turn\s+\d+|rounding|decimal|amounts?|totals?"
    r"|results?|values?|inputs?|logging|tests?|[a-z]\w*[_.]\w+|\d[\d.]*)\b"
)
_CLAUSE_END = (
    r"(?=\s*(?:[)!?]|\.(?:\s|$)|$)|\s*[;:(](?!\s*" + _CONTINUES + r")"
    r"|\s*,\s*(?:(?:and|but|so|while|whereas)\s+)?" + _NEW_SUBJECT + r"|\s+(?:and|but|so|while|whereas)\s+" + _NEW_SUBJECT + r")"
)
_CLAUSE_START = re.compile(r"(?:^|[;:(,]|\b(?:and|but|so|while|whereas)\b)\s*(?:[-*]\s+|\d+\.\s+)?")
_NON_CURRENT = (
    # A withdrawal: "ROUND_HALF_UP was superseded by that correction", "That correction overrides ROUND_HALF_UP",
    # "Replace the old ROUND_HALF_UP with ...", ", replacing ROUND_HALF_UP", "was not replaced until seq 7".
    _RULE_HEAD + r"\s+" + _PASSIVE + r"\s+(?:" + _WHEN + r"\s+)?{wd}" + _ADJUNCTS + _TAIL,
    _RULE_HEAD + r"\s+(?:was|were|had)\s+(?:not|never)\s+(?:been\s+)?{wd}\s+(?:until|till|before)\s+" + _FREE + _TAIL,
    r"(?:" + _FREE + r"\s+(?=\w+(?:ed|es)\b))?{wd}\s+" + _RULE_REF + _ADJUNCTS + _TAIL,
    # A non-current predicate.
    _RULE_HEAD + r"\s+" + _NOT_IN_USE + _ADJUNCTS + _TAIL,
    # A protective instruction: a negated current use, "stop using ...", "do not replace ROUND_HALF_EVEN with ...".
    r"(?:do\s+not|don't|never|must\s+not|mustn't|should\s+not|shouldn't|no\s+longer)\s+(?:" + "|".join(_USE_OBJECT) + r")"
    + _HEAD_NOUN + _ADJUNCTS + _TAIL,
    r"(?:stop|stops|stopped|avoid|avoids|avoided|cease|ceases|ceased)\s+(?:using|applying|keeping|(?:rounding|quanti[sz]ing)\s+(?:with|using|by))\s+"
    + _RULE_REF + _ADJUNCTS + _TAIL,
    r"(?:do\s+not|don't|never)\s+(?:replace|swap|change|switch)\s+" + _FREE + r"\s+(?:with|for|to|back\s+to)\s+" + _RULE_REF + _ADJUNCTS + _TAIL,
    _FREE + r"\s+(?:(?:is|are|was|were)\s+" + _NOT_NOW + r"\s+(?:being\s+)?|(?:(?:must|should|shall|will|can|may)\s+" + _NOT_NOW
    + r"|mustn't|shouldn't|can't|cannot|won't)\s+be\s+)" + _ROUNDED + r"\s+" + _ROUND_COMPLEMENT + _RULE_REF + _ADJUNCTS + _TAIL,
    # A contrast: "Rounding is ROUND_HALF_EVEN, not ROUND_HALF_UP", "(not ROUND_HALF_UP)", "... instead of ROUND_HALF_UP
    # in calc.py", "ROUND_HALF_EVEN rather than the old ROUND_HALF_UP applies", "Instead of rounding with ROUND_HALF_UP, ...".
    r"(?:" + _FREE + r"\s*,?\s+)?(?:not|never)\s+" + _RULE_REF + _ADJUNCTS + _TAIL,
    r"(?:" + _FREE + r"\s+)?(?:instead\s+of|rather\s+than)\s+" + _BY_USING + _RULE_REF
    + r"(?:\s+(?:is|are)\s+(?:now\s+)?(?:used|applied|the\s+(?:current\s+)?(?:rounding\s+)?(?:rule|mode))|\s+(?:now\s+)?(?:applies|governs))?"
    + _ADJUNCTS + _TAIL,
    r"(?:instead\s+of|rather\s+than)\s+" + _BY_USING + _RULE_REF + r"\s*,?\s+" + _FREE + _TAIL,
    # A past use with its supersession, or a past identity: "Seq 1 used ROUND_HALF_UP, which was later superseded",
    # "Rounding was ROUND_HALF_UP", "The old rounding mode is ROUND_HALF_UP", "The rounding mode is no longer ROUND_HALF_UP".
    r"(?:" + _FREE + r"\s+)?(?:used|applied|relied\s+on|had\s+used|(?:rounded|quanti[sz]ed)\s+(?:with|using|by))\s+" + _RULE_REF + _ADJUNCTS
    + r"(?:" + _RELATIVE + "|" + _ANAPHORIC + r")" + _TRAILERS,
    r"(?:" + _FREE + r"\s+)?(?:(?:was|were)(?:\s+(?:previously|formerly|originally|initially|once))?|used\s+to\s+be|previously|formerly"
    r"|originally|initially)\s+" + _RULE_REF + _ADJUNCTS + _TAIL,
    r"(?:the\s+)?" + _STALE + r"\s+(?:rounding\s+)?(?:mode|rule|one|default|setting)\s+(?:is|was)\s+" + _RULE_REF + _ADJUNCTS + _TAIL,
    r"(?:the\s+)?(?:current\s+)?(?:rounding(?:\s+(?:mode|rule))?|mode|rule)\s+(?:is|was)\s+(?:no\s+longer|not)\s+" + _RULE_REF + _ADJUNCTS + _TAIL,
    # A transition: "changed from ROUND_HALF_UP to ...", "ROUND_HALF_UP -> ROUND_HALF_EVEN", "ROUND_HALF_UP; now ROUND_HALF_EVEN".
    r"(?:" + _FREE + r"\s+)?(?:{wd}|changes|change|moved|moves|move|switched|switches|switch|went)\s+"
    r"(?:(?:the\s+)?(?:rounding(?:\s+(?:mode|rule))?|mode|rule)\s+|it\s+)?from\s+" + _RULE_REF
    + r"(?:\s+to\s+" + _FREE + r")?" + _ADJUNCTS + _TAIL,
    _RULE_REF + r"\s*(?:->|=>|→)\s*" + _FREE + _TAIL,
    _RULE_REF + r"\s*[;,]\s*now\s+" + _FREE + _TAIL,
)


def _non_current(rule: str, rules: FactRules) -> list[re.Pattern[str]]:
    """The supported non-current constructions for one superseded rule, each ending at a clause end."""
    withdrawal = r"\b(?:" + "|".join(f"(?:{verb})\\w*" for verb in rules.verbs) + ")"
    return [re.compile("(?:" + template.format(rule=re.escape(rule), wd=withdrawal) + ")" + _CLAUSE_END) for template in _NON_CURRENT]


def _accounted(sentence: str, constructions: Sequence[re.Pattern[str]]) -> list[tuple[int, int]]:
    """The spans of `sentence` that a supported construction covers, each from a clause start to a clause end."""
    starts = sorted({match.end() for match in _CLAUSE_START.finditer(sentence)})
    return [found.span() for start in starts for pattern in constructions if (found := pattern.match(sentence, start)) is not None]


def _states_supersession(statement: str, rules: FactRules) -> bool:
    """A fixture marker, or a fixture verb no adjacent negation reverses, inside one accounted statement."""
    return any(_asserted(marker, statement, ()) for marker in rules.markers) or any(
        _asserted(verb, statement, (rules.verb_negation,)) for verb in rules.verbs
    )


def _normalized(text: str) -> str:
    """Lower-cased, whitespace collapsed, one terminal period dropped."""
    collapsed = " ".join(text.lower().split())
    return collapsed.removesuffix(".")


def _created(event: str, *, passive: bool) -> tuple[str, str] | None:
    """The (artifact, payload) of a normalized creation event, active or (if allowed) passive."""
    for pattern in (_ACTIVE_CREATION, _PASSIVE_CREATION) if passive else (_ACTIVE_CREATION,):
        match = pattern.fullmatch(event)
        if match is not None:
            return match.group(1), match.group(2)
    return None


@dataclass(frozen=True, slots=True)
class SourceHistory:
    """The source events validator v5 may accept as history: every summarized turn before the correction
    whose outcome is completed, whose effect is complete and whose completion is a creation event,
    as (artifact, payload) by sequence. Derived from the fixture, never from a summary; missing or
    other outcome or effect evidence contributes nothing."""

    correction_seq: int
    creations: Mapping[int, tuple[str, str]]

    def excuses(self, sentence: str) -> bool:
        match = _DATED.fullmatch(_normalized(sentence))
        if match is None:
            return False
        seq = int(match.group(1))
        recorded = self.creations.get(seq)
        return seq < self.correction_seq and recorded is not None and _created(match.group(2), passive=True) == recorded


def _source_history(raw_turns: Sequence[Mapping[str, Any]], summarized: set[int], correction_seq: int) -> SourceHistory:
    creations = {}
    for turn in raw_turns:
        seq = turn["seq"]
        if seq in summarized and seq < correction_seq and turn.get("outcome") == "completed" and turn.get("effect_state") == "complete":
            event = _created(_normalized(turn["completion_text"]), passive=False)
            if event is not None:
                creations[seq] = event
    return SourceHistory(correction_seq=correction_seq, creations=MappingProxyType(creations))


def fixture_digest(raw: Mapping[str, Any]) -> str:
    """The fixture's identity: its canonical JSON, independent of key order, whitespace and line
    endings, so a receipt never depends on how a checkout stores the file."""
    canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_fixture(path: Path = FIXTURE_PATH) -> Fixture:
    raw = json.loads(path.read_bytes().decode("utf-8"))
    try:
        turns = {t["seq"]: OrdinaryTurn(t["seq"], t["user_prompt"], t["plan_text"], t["completion_text"]) for t in raw["turns"]}
        ev = raw["evaluation"]
        step1, step2, tail = tuple(ev["step1_turns"]), tuple(ev["step2_turns"]), tuple(ev["exact_tail_turns"])
        constraints_turn, correction_turn, max_output_tokens = ev["constraints_turn"], ev["correction_turn"], int(ev["max_output_tokens"])
        rules = FactRules(
            negation=raw["negation"],
            reported=raw["reported_speech"],
            markers=tuple(raw["supersession_markers"]),
            verbs=tuple(raw["supersession_verbs"]),
            verb_negation=raw["verb_negation"],
            forbidden=tuple(raw["forbidden"]),
        )
        step1_facts, final_facts, name = tuple(raw["step1_facts"]), tuple(raw["final_facts"]), raw["fixture"]
    except KeyError as exc:
        raise ValueError(f"the fixture lacks {exc}") from exc
    ordered = tuple(sorted(turns))
    if step1 + step2 + tail != ordered:
        raise ValueError("the fixture's steps and tail must partition its turns in order")
    if constraints_turn not in step1 or correction_turn not in step2:
        raise ValueError("the early constraints must lie in step 1 and the correction in step 2, both summarized")
    return Fixture(
        name=name,
        digest=fixture_digest(raw),
        turns=turns,
        step1=step1,
        step2=step2,
        tail=tail,
        max_output_tokens=max_output_tokens,
        step1_facts=step1_facts,
        final_facts=final_facts,
        rules=rules,
        history=_source_history(raw["turns"], set(step1 + step2), correction_turn),
    )


# --- The fact report -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FactCheck:
    id: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class FactReport:
    checks: tuple[FactCheck, ...]

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "checks": [{"id": c.id, "passed": c.passed, "detail": c.detail} for c in self.checks]}


def _asserted(pattern: str, span: str, governors: Sequence[str]) -> list[str]:
    """The matches of `pattern` in `span` that no governor governs.

    A governor (a negation, or reported speech) governs only the next match after it, and only when
    its pattern, anchored at the match, finds it close enough, with no comma, clause end or
    contrastive conjunction between. So "was not approved" is not an approval claim, while "not
    reviewed but approved" and "...not approved and every plan was approved" are (Codex CP2 R2). A
    governed match carries over a coordinated next match: "not approved or granted"."""
    found: list[str] = []
    previous, governed = 0, False
    for match in re.finditer(pattern, span):
        segment = span[previous : match.start()]
        governed = (governed and _COORDINATED.fullmatch(segment) is not None) or any(re.search(governor, segment) for governor in governors)
        if not governed:
            found.append(match.group(0))
        previous = match.end()
    return found


def evaluate_summary(
    text: str | None,
    finish_status: str | None,
    facts: Sequence[Mapping[str, Any]],
    rules: FactRules,
    *,
    history: SourceHistory | None = None,
) -> FactReport:
    """The fact report. `history` is the fixture's trusted source history; without it no mention of a
    superseded rule is excused as a historical record."""
    checks = [FactCheck("finished", finish_status == "stop", f"finish status {finish_status!r}")]
    try:
        sections = parse_summary(text or "")
    except SummaryFormatError as exc:
        return FactReport(tuple([*checks, FactCheck("format", False, str(exc))]))
    checks.append(FactCheck("format", True, SUMMARY_FORMAT))
    lower = (text or "").lower()
    # Sentences, so a marker elsewhere on a line cannot excuse a stale rule; clauses, so a negation
    # in one clause cannot reach another clause's claim.
    sentences = [part for part in _SENTENCE.split(lower) if part.strip()]
    clauses = [part for sentence in sentences for part in sentence.split(_CLAUSE) if part.strip()]
    negation = (rules.negation,)
    for fact in facts:
        if "affirm" in fact:
            # Polarity: a fact is stated only by an affirmative match no negation governs, and any
            # ungoverned contradiction fails it ("do not use Decimal", "eval ... not forbidden",
            # "negative inputs are unsupported"). The patterns state the constraint itself, so a
            # bare word ("a decimal currency calculator", "evaluate") never counts. An identifier
            # fact ("governed": false) is stated even under a protective negation ("never rename
            # calculate(a, op, b)"); its withdrawals are deny patterns.
            governors = negation if fact.get("governed", True) else ()
            stated = [found for clause in clauses for found in _asserted(fact["affirm"], clause, governors)]
            denied = [found for clause in clauses for found in _asserted(fact["deny"], clause, negation)] if "deny" in fact else []
            if denied:
                detail = f"contradicted: {denied[0]!r}"
            else:
                detail = f"stated: {stated[0]!r}" if stated else "not stated"
            checks.append(FactCheck(fact["id"], bool(stated) and not denied, detail))
        elif "superseded" in fact:
            rule = fact["superseded"]
            # Each sentence that mentions the rule, with its section.
            mentions = [
                (name, sentence)
                for name, body in zip(SECTIONS, sections.bodies, strict=True)
                for sentence in _SENTENCE.split(body.lower())
                if rule in sentence
            ]
            current = [pattern.format(rule=re.escape(rule)) for pattern in _CURRENT_USE]
            asserted = [sentence for _, sentence in mentions if any(_asserted(pattern, sentence, (*negation, _CONTRAST)) for pattern in current)]
            # Every occurrence must lie inside a supported non-current statement or an exact dated source
            # record; the supersession must be stated inside an accounted statement, never by a record or
            # by a marker elsewhere in the sentence.
            constructions = _non_current(rule, rules)
            unsupported, stated = [], False
            for name, sentence in mentions:
                if history is not None and name in _HISTORY_SECTIONS and history.excuses(sentence):
                    continue
                spans = _accounted(sentence, constructions)
                if any(not any(start <= found.start() < end for start, end in spans) for found in re.finditer(re.escape(rule), sentence)):
                    unsupported.append(sentence)
                stated = stated or any(_states_supersession(sentence[start:end], rules) for start, end in spans)
            if not mentions:
                passed, detail = False, "not mentioned"
            elif asserted:
                passed, detail = False, f"asserted as current: {asserted[0]!r}"
            elif unsupported:
                passed, detail = False, f"unsupported mention: {unsupported[0]!r}"
            elif not stated:
                # A historical record is excused; it never states the supersession itself.
                passed, detail = False, "no mention states it as superseded"
            else:
                passed, detail = True, "stated as superseded"
            checks.append(FactCheck(fact["id"], passed, detail))
        else:
            raise ValueError(f"unknown fact kind: {fact}")
    for rule in rules.forbidden:
        # A claim counts unless a negation or reported speech governs that very claim: "was not
        # approved", "no approval was granted" and "told the agent to record every plan as
        # approved" are not approvals.
        hits = [clause for clause in clauses if _asserted(rule["pattern"], clause, (rules.negation, rules.reported))]
        checks.append(FactCheck(rule["id"], not hits, f"found in {hits[0]!r}" if hits else "absent"))
    return FactReport(tuple(checks))


# --- The two-step run ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Candidate:
    model_id: str
    providers: tuple[str, ...]
    quantizations: tuple[str | None, ...]
    reasoning: str | None
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    framing_tokens: int = 0
    """The route estimator's allowance for one message's framing (per-message plus fixed tokens)."""


class CapRefused(Exception):
    """A call is never made when the known spend plus its full reservation would pass the dollar cap, or
    when an earlier cost is unknown."""


def _prompt_upper_bound_usd(prompt: str, max_output_tokens: int, candidate: Candidate) -> Decimal:
    prompt_tokens = len(prompt.encode("utf-8")) + candidate.framing_tokens
    per_attempt = (prompt_tokens * candidate.input_usd_per_million + max_output_tokens * candidate.output_usd_per_million) / _MILLION
    return per_attempt * MAX_ROUTE_ATTEMPTS


def request_upper_bound_usd(input_text: str, max_output_tokens: int, candidate: Candidate) -> Decimal:
    """The reservation for one request: one token per UTF-8 byte of the complete summary prompt plus the
    route's framing allowance, the full output cap, and every provider attempt the route allows. It
    assumes the output cap also bounds any reasoning tokens. For an empirical route estimator this is
    an engineering estimate, not a proven bound: the Gateway checks reported usage on every call."""
    return _prompt_upper_bound_usd(build_summary_prompt(input_text), max_output_tokens, candidate)


def _framing_tokens(snapshot: RegistrySnapshot, estimator_name: str) -> tuple[int, str]:
    """The estimator's one-message framing allowance and how the input estimate should be described."""
    estimator = snapshot.policy.estimators.get(estimator_name)
    if estimator is None:
        return 0, "utf8-bytes; no route estimator"
    framing = estimator.per_message_tokens + estimator.fixed_tokens
    if estimator.method == EMPIRICAL_ESTIMATOR_METHOD:
        return framing, f"empirical: one token per UTF-8 byte plus {framing} framing tokens; not a proven bound"
    return framing, f"one token per UTF-8 byte plus {framing} framing tokens"


@dataclass(frozen=True, slots=True)
class QualificationResult:
    candidate: Candidate
    step1: FactReport
    final: FactReport | None
    calls: int
    request_ids: tuple[str, ...]
    reported_cost_usd: Decimal | None
    receipt: dict[str, Any] | None
    # One receipt per provider attempt, from the runtime's callback: the evidence a paid run keeps.
    attempts: tuple[MaintenanceReceipt, ...] = ()
    unrun: str | None = None
    """Why step 2 was not run although step 1 passed, if so."""
    budget: str | None = None
    """Why the run is not a success on budget grounds, whatever its quality findings: the known spend
    exceeds the cap, the spend is unknown, or too little budget was left for step 2."""
    inadmissible: str | None = None
    """Why the final summary would be refused at runtime, whatever its fact report: over the byte bound.
    A run control beside the validator, which is unchanged."""

    @property
    def passed(self) -> bool:
        quality = self.final is not None and self.step1.passed and self.final.passed
        return quality and self.budget is None and self.inadmissible is None


def run_qualification(
    fixture: Fixture,
    candidate: Candidate,
    summarize: SummarizerCall,
    *,
    dollar_cap: Decimal,
    recorded_on: str,
    registry_hash: str | None = None,
    on_receipt: Callable[[MaintenanceReceipt], None] | None = None,
) -> QualificationResult:
    """`on_receipt` receives each attempt's receipt as it is recorded, so a caller keeps them even if
    the run then raises."""
    turns = fixture.turns
    calls = 0
    receipts: list[MaintenanceReceipt] = []

    def record(receipt: MaintenanceReceipt) -> None:
        receipts.append(receipt)
        if on_receipt is not None:
            on_receipt(receipt)

    def known_spend() -> Decimal | None:
        """Every physical attempt settled at its reported cost; None once any cost is unknown."""
        costs = [r.cost_usd for r in receipts]
        return None if any(cost is None for cost in costs) else sum(costs, Decimal(0))  # type: ignore[arg-type]

    def unaffordable(prompt: str, max_output_tokens: int, label: str) -> str | None:
        """Why a request may not be sent: the known spend plus its full reservation (every safe resend
        included) must fit the cap, and an unknown spend stops further dispatch (Codex correction-batch
        review M3). A charge already made cannot be undone; the next call can be prevented."""
        spent = known_spend()
        if spent is None:
            return "an earlier attempt's cost is unknown, so the remaining budget is unknown"
        bound = _prompt_upper_bound_usd(prompt, max_output_tokens, candidate)
        if spent + bound > dollar_cap:
            return f"known spend {spent} USD plus {label}'s reservation {bound} USD exceeds the {dollar_cap} USD cap"
        return None

    def capped(*, prompt: str, max_output_tokens: int) -> SummarizerResponse:
        """The candidate call, made only within the call and dollar caps."""
        nonlocal calls
        if calls >= MAX_FIXTURE_CALLS:
            raise CapRefused("the fixture allows two calls per candidate")
        refused = unaffordable(prompt, max_output_tokens, "this request")
        if refused is not None:
            raise CapRefused(refused)
        calls += 1
        return summarize(prompt=prompt, max_output_tokens=max_output_tokens)

    # The runtime's own callback: completed-attempt rule, re-sanitizing and a receipt per attempt
    # (Fable CP2 review). The fixture is synthetic, so there are no secrets to supply.
    host = HostMaintenance(
        call=capped,
        sanitizer=ConversationSanitizer(ConversationSanitizerInputs(known_secrets=(), path_aliases=())),
        identity=MaintenanceIdentity(
            session_id=f"qualification:{fixture.name}",
            turn_seq=0,
            model_id=candidate.model_id,
            role=Role.SUMMARIZER.value,
            route=candidate.providers,
            reasoning=candidate.reasoning,
            quantizations=candidate.quantizations,
            strategy="compaction",
            revision_digest=fixture.digest,
            registry_hash=registry_hash,
        ),
        record_receipt=record,
        cancelled=lambda: False,
    )

    def step(input_text: str, covered: tuple[int, ...]):
        return host(
            MaintenanceRequest(
                input_text=input_text,
                covered_turn_ids=covered,
                max_output_tokens=fixture.max_output_tokens,
                prompt_version=PROMPT_VERSION,
                format_version=SUMMARY_FORMAT,
            )
        )

    first = step(maintenance_input(None, [turns[seq] for seq in fixture.step1]), fixture.step1)
    step1 = evaluate_summary(first.summary_text, first.finish_status, fixture.step1_facts, fixture.rules, history=fixture.history)
    final, unrun, budget, inadmissible = None, None, None, None
    if step1.passed:
        carried = len((first.summary_text or "").encode("utf-8"))
        # Merge the step 1 summary with the newer turns, as the runtime's incremental path does.
        step2_input = maintenance_input(first.summary_text, [turns[seq] for seq in fixture.step2])
        if carried > SUMMARY_MAX_BYTES:
            unrun = f"step 2 UNRUN: the step 1 summary is {carried} UTF-8 bytes, over the {SUMMARY_MAX_BYTES}-byte carry ceiling"
        elif (refused := unaffordable(build_summary_prompt(step2_input), fixture.max_output_tokens, "step 2")) is not None:
            unrun = budget = f"step 2 UNRUN: {refused}"
        else:
            second = step(step2_input, fixture.step1 + fixture.step2)
            final = evaluate_summary(second.summary_text, second.finish_status, fixture.final_facts, fixture.rules, history=fixture.history)
            # The exact sanitized text the runtime would store, measured before any receipt.
            stored = len((second.summary_text or "").encode("utf-8"))
            if stored > SUMMARY_MAX_BYTES:
                inadmissible = f"the final summary is {stored} UTF-8 bytes, over the {SUMMARY_MAX_BYTES}-byte runtime bound"
    request_ids = tuple(r.gateway_request_id for r in receipts if r.gateway_request_id)
    reported = known_spend()
    if reported is not None and reported > dollar_cap:
        budget = f"known spend {reported} USD exceeds the {dollar_cap} USD cap"
    elif reported is None and final is not None:
        budget = "the run's total cost is unknown"
    result = QualificationResult(candidate, step1, final, calls, request_ids, reported, None, tuple(receipts), unrun, budget, inadmissible)
    if not result.passed:
        return result
    receipt = {
        "model_id": candidate.model_id,
        "format": SUMMARY_FORMAT,
        "providers": list(candidate.providers),
        "quantizations": list(candidate.quantizations),
        "reasoning": candidate.reasoning,
        "fixture_digest": fixture.digest,
        "prompt_digest": PROMPT_DIGEST,
        "validator": VALIDATOR_VERSION,
        "request_ids": list(request_ids),
        "recorded_on": recorded_on,
        "result": "pass",
    }
    return QualificationResult(candidate, step1, final, calls, request_ids, reported, receipt, tuple(receipts), unrun, budget, inadmissible)


# --- The paid envelope ---------------------------------------------------------------------------------


def _candidate(snapshot: RegistrySnapshot, model_id: str) -> Candidate:
    entry = snapshot.policy.models[model_id]
    return Candidate(
        model_id=model_id,
        providers=entry.route.providers,
        quantizations=entry.route.quantizations,
        reasoning=entry.default_reasoning,
        input_usd_per_million=entry.prices.input_usd_per_million,
        output_usd_per_million=entry.prices.output_usd_per_million,
        framing_tokens=_framing_tokens(snapshot, entry.route.estimator)[0],
    )


RESERVATION_BASIS = (
    "empirical engineering reservation, not a universal upper bound: each request at its input estimate "
    "(step 2 carrying a summary at the byte ceiling), the full output cap and every provider attempt; "
    "a provider charge after a failed check cannot be undone"
)


def paid_envelope(snapshot: RegistrySnapshot, fixture: Fixture) -> list[dict[str, Any]]:
    """Per assigned summarizer: what approving its two fixture requests would authorize."""
    issues = validate_registry(snapshot)
    step1_input = maintenance_input(None, [fixture.turns[seq] for seq in fixture.step1])
    # Step 2 carries the step 1 summary, at most the carry ceiling in bytes (a longer one is not sent).
    step2_input = maintenance_input("a" * SUMMARY_MAX_BYTES, [fixture.turns[seq] for seq in fixture.step2])
    envelope = []
    for model_id in ordered_assignments(snapshot, Role.SUMMARIZER):
        candidate = _candidate(snapshot, model_id)
        framing, estimate = _framing_tokens(snapshot, snapshot.policy.models[model_id].route.estimator)
        blockers = sorted(
            issue.code
            for issue in issues
            if issue.model_id == model_id and issue.role in (None, Role.SUMMARIZER) and issue.code != "SUMMARIZER_UNQUALIFIED"
        )
        step1_bound = request_upper_bound_usd(step1_input, fixture.max_output_tokens, candidate)
        step2_bound = request_upper_bound_usd(step2_input, fixture.max_output_tokens, candidate)
        envelope.append(
            {
                "model_id": model_id,
                "providers": list(candidate.providers),
                "quantizations": list(candidate.quantizations),
                "reasoning": candidate.reasoning,
                "structurally_eligible": not blockers,
                "blockers": blockers,
                "requests": MAX_FIXTURE_CALLS,
                "max_provider_attempts_per_request": MAX_ROUTE_ATTEMPTS,
                "max_output_tokens": fixture.max_output_tokens,
                "carried_summary_max_bytes": SUMMARY_MAX_BYTES,
                "input_estimate": estimate,
                "reservation_basis": RESERVATION_BASIS,
                "input_token_reservations": [
                    len(build_summary_prompt(step1_input).encode("utf-8")) + framing,
                    len(build_summary_prompt(step2_input).encode("utf-8")) + framing,
                ],
                "input_usd_per_million": str(candidate.input_usd_per_million),
                "output_usd_per_million": str(candidate.output_usd_per_million),
                "reserved_cost_usd": str(step1_bound + step2_bound),
                "fixture_digest": fixture.digest,
                "prompt_digest": PROMPT_DIGEST,
                "validator": VALIDATOR_VERSION,
                "receipt_fields": list(SummaryReceipt.model_fields),
            }
        )
    return envelope


# --- The paid run --------------------------------------------------------------------------------------

LIVE_PROFILE = "qualification"
# The operator's $0.10 (2026-10-09) is the cumulative Stage B ceiling: run 1 (fixture v1) already spent
# $0.0006881, so this run may spend the rest (Codex Stage B v2 disposition, qualification 5).
STAGE_B_CEILING = Decimal("0.10")
PRIOR_STAGE_B_SPEND = Decimal("0.0006881")
PRIOR_STAGE_B_RUN = "stage-b-qualification/run-1: fixture v1, FAIL at step 1, one attempt, $0.0006881"
LIVE_DOLLAR_CAP = STAGE_B_CEILING - PRIOR_STAGE_B_SPEND
LIVE_WALL_CLOCK_SECONDS = 30 * 60  # the released 30-minute limit
LIVE_REQUEST_TIMEOUT_SECONDS = 300.0  # a request starts only if it can time out inside the limit
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _gateway_settings(environ: Mapping[str, str]) -> OptimusGatewaySettings:
    """The host's own Gateway credentials: OPTIMUS_API_KEY, or else the shared secret the launch
    resolves (environment, `.env.gateway` or keyring), as the host does."""
    env = dict(environ)
    if not env.get("OPTIMUS_API_KEY", "").strip():
        secret = resolve_shared_secret(env, config_root=resolve_config_root(workspace_root=_REPO_ROOT, environ=env))
        if secret:
            env["OPTIMUS_API_KEY"] = secret
    return OptimusGatewaySettings.from_env(env)


def _write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, default=str)
        handle.write("\n")


def _append_json(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


# Persisted as-is: identifiers this host or its Gateway minted, the attempt classification, numbers
# written as strings, and the requested model and Gateway provider (this run's own configuration).
# The evidence sanitizer's entropy rule would otherwise erase the identifiers that link attempts to the
# receipt. Every other string can carry provider-supplied text (Codex correction-batch review M4).
_UNREDACTED_KEYS = frozenset({"attempt_id", "gateway_request_id", "outcome", "cost_usd", "recorded_at", "model", "provider"})


def _redacted(value: Any, sanitizer: ConversationSanitizer, key: str | None = None) -> Any:
    """`value` with every string not under an unredacted key passed through the evidence sanitizer;
    structure, numbers and the attempt classification are kept. Only what is written is redacted: the
    runtime compares the raw values in memory."""
    if isinstance(value, dict):
        return {name: _redacted(item, sanitizer, name) for name, item in value.items()}
    if isinstance(value, list | tuple):
        return [_redacted(item, sanitizer, key) for item in value]
    if isinstance(value, str) and key not in _UNREDACTED_KEYS:
        return sanitizer.sanitize(value)
    return value


def _receipt_record(receipt: MaintenanceReceipt, sanitizer: ConversationSanitizer) -> dict[str, Any]:
    usage = receipt.gateway_usage
    record = {
        "attempt_id": receipt.attempt_id,
        "gateway_request_id": receipt.gateway_request_id,
        "outcome": receipt.outcome,
        "cost_usd": None if receipt.cost_usd is None else str(receipt.cost_usd),
        "finish_status": receipt.finish_status,
        "covered_turn_ids": list(receipt.covered_turn_ids),
        "recorded_at": receipt.recorded_at.isoformat(),
        "provider_request_id": receipt.provider_request_id,
        "http_status": receipt.http_status,
        "provider": receipt.provider,
        "resolved_provider": receipt.resolved_provider,
        "resolved_model": receipt.resolved_model,
        "usage": None if usage is None else usage.model_dump(mode="json"),
    }
    return _redacted(record, sanitizer)


def _evidence_sanitizer(*known_secrets: str) -> ConversationSanitizer:
    """The runtime's evidence-redaction sanitizer (the one maintenance summaries pass through), for
    every free text the run persists."""
    return ConversationSanitizer(ConversationSanitizerInputs(known_secrets=known_secrets, path_aliases=()))


def _error_text(exc: BaseException, sanitizer: ConversationSanitizer) -> str:
    text = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
    return sanitizer.sanitize(text)


def _refuse(reason: str) -> int:
    print(f"evaluate_context_summarizer run: REFUSED before any request: {reason}", file=sys.stderr)
    return 2


def run_live(
    *,
    out: Path,
    host_pid: int,
    gateway_pid: int,
    environ: Mapping[str, str],
    recorded_on: str,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """The paid two-request qualification of the reviewed profile through the operator-started host's
    Gateway. Exit 0: both steps passed within the cap and a receipt candidate was written; 1: the run
    failed on quality, on budget or stopped (its evidence is kept); 2: refused before any request.

    `out` is a new directory: `run.json` (identity, written before the first dispatch),
    `attempts.jsonl` and `responses.jsonl` (appended as they arrive), `outcome.json` (always, last) and
    `receipt-candidate.json` (a pass only; it qualifies nothing until reviewed)."""
    if out.exists():
        return _refuse(f"{out} exists; every run gets a new directory")
    fixture = load_fixture()
    snapshot = compose_test_profile_snapshot(LIVE_PROFILE)
    envelope = paid_envelope(snapshot, fixture)
    if len(envelope) != 1:
        return _refuse("the profile must assign exactly one summarizer")
    [row] = envelope
    model_id = row["model_id"]
    route = experimental_route(snapshot, model_id)
    if route is None:
        return _refuse("the composed profile is not the reviewed experimental route")
    if not row["structurally_eligible"]:
        return _refuse(f"the summarizer is not structurally eligible: {row['blockers']}")
    if Decimal(row["reserved_cost_usd"]) > LIVE_DOLLAR_CAP:
        return _refuse(f"the reservation {row['reserved_cost_usd']} USD exceeds the {LIVE_DOLLAR_CAP} USD cap")
    try:
        settings = _gateway_settings(environ)
    except ValueError as exc:
        return _refuse(f"no usable Gateway credentials ({_error_text(exc, _evidence_sanitizer())})")
    shared_secret = settings.optimus_api_key.get_secret_value()
    evidence = _evidence_sanitizer(shared_secret)

    candidate = _candidate(snapshot, model_id)
    run_id = uuid.uuid4().hex
    identity = MaintenanceIdentity(
        session_id=f"qualification:{fixture.name}:{run_id}",
        turn_seq=0,
        model_id=model_id,
        role=Role.SUMMARIZER.value,
        route=candidate.providers,
        reasoning=candidate.reasoning,
        quantizations=candidate.quantizations,
        strategy="compaction",
        revision_digest=fixture.digest,
        registry_hash=snapshot.effective_hash,
    )
    bind_turn = gateway_summarizer_factory(
        gateway_client=GatewayClient(settings=settings, timeout_seconds=LIVE_REQUEST_TIMEOUT_SECONDS),
        route=SummarizerRoute(model_id, identity.role, identity.route, identity.reasoning, identity.quantizations),
        snapshot=snapshot,
        disclosure_key=disclosure_key(shared_secret),
    )
    summarize = bind_turn(identity, lambda _notice: False)  # a route needing a notice sends nothing

    out.mkdir(parents=True)
    deadline = clock() + LIVE_WALL_CLOCK_SECONDS
    sent = {"dispatched": 0, "returned": 0}

    def call(*, prompt: str, max_output_tokens: int) -> SummarizerResponse:
        if deadline - clock() < LIVE_REQUEST_TIMEOUT_SECONDS:
            raise CapRefused("the 30-minute wall clock leaves too little time for another request")
        sent["dispatched"] += 1
        response = summarize(prompt=prompt, max_output_tokens=max_output_tokens)
        # The response and its attempts' billing reach disk before the runtime records receipts; until
        # then the request counts as in flight, at unknown cost.
        _append_json(
            out / "responses.jsonl",
            {
                "request": sent["dispatched"],
                "text": None if response.text is None else evidence.sanitize(response.text),
                "finish_status": response.finish_status,
                "attempts": [
                    {
                        "attempt_id": attempt.attempt_id,
                        "gateway_request_id": attempt.gateway_request_id,
                        "outcome": attempt.outcome,
                        "cost_usd": None if attempt.cost_usd is None else str(attempt.cost_usd),
                    }
                    for attempt in response.attempts
                ],
            },
        )
        sent["returned"] += 1
        return response

    _write_json(
        out / "run.json",
        {
            "run_id": run_id,
            "started_at": datetime.now(UTC).isoformat(),
            "profile": LIVE_PROFILE,
            "registry_hash": snapshot.effective_hash,
            "experimental_route": {"provider_family": route.provider_family, "provider_name": route.provider_name},
            "model_id": model_id,
            "providers": list(candidate.providers),
            "quantizations": list(candidate.quantizations),
            "reasoning": candidate.reasoning,
            "envelope": row,
            "fixture": fixture.name,
            "fixture_file_sha256": hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest(),
            "dollar_cap_usd": str(LIVE_DOLLAR_CAP),
            "stage_b_ceiling_usd": str(STAGE_B_CEILING),
            "prior_stage_b_spend_usd": str(PRIOR_STAGE_B_SPEND),
            "prior_stage_b_run": PRIOR_STAGE_B_RUN,
            "wall_clock_seconds": LIVE_WALL_CLOCK_SECONDS,
            "request_timeout_seconds": LIVE_REQUEST_TIMEOUT_SECONDS,
            "max_requests": MAX_FIXTURE_CALLS,
            "max_provider_attempts": MAX_FIXTURE_CALLS * MAX_ROUTE_ATTEMPTS,
            "gateway_url": settings.gateway_url,
            "host_pid": host_pid,
            "gateway_pid": gateway_pid,
            "process_identity": "operator-stated; the Gateway's binding check refuses any other approved snapshot",
            "exclusive_use": "no other model client may use this Gateway during the run",
            "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
    )
    try:
        result = run_qualification(
            fixture,
            candidate,
            call,
            dollar_cap=LIVE_DOLLAR_CAP,
            recorded_on=recorded_on,
            registry_hash=snapshot.effective_hash,
            on_receipt=lambda receipt: _append_json(out / "attempts.jsonl", _receipt_record(receipt, evidence)),
        )
    except BaseException as exc:
        # Every attempt already recorded stays on disk; an interrupted request's cost is unknown.
        _write_json(
            out / "outcome.json",
            {
                "status": "stopped",
                "error": _error_text(exc, evidence),
                "requests_dispatched": sent["dispatched"],
                "in_flight": sent["dispatched"] > sent["returned"],
                "receipt": None,
            },
        )
        if isinstance(exc, Exception):
            return 1
        raise

    known = result.reported_cost_usd
    passed = result.passed and known is not None and known <= LIVE_DOLLAR_CAP and len(result.attempts) <= MAX_FIXTURE_CALLS * MAX_ROUTE_ATTEMPTS
    if passed:
        usages = [r.gateway_usage for r in result.attempts if r.outcome == "completed" and r.gateway_usage is not None]
        _write_json(
            out / "receipt-candidate.json",
            {
                "receipt": result.receipt,
                "observed": _redacted(
                    {
                        "resolved_providers": [usage.resolved_provider for usage in usages],
                        "resolved_models": [usage.resolved_model for usage in usages],
                        "reasoning_tokens": [usage.reasoning_tokens for usage in usages],
                    },
                    evidence,
                ),
                "note": "a candidate for review: it qualifies nothing and enables no attached engine by itself",
            },
        )
    _write_json(
        out / "outcome.json",
        {
            "status": "pass" if passed else ("budget" if result.budget is not None else "fail"),
            "step1": result.step1.to_dict(),
            "final": None if result.final is None else result.final.to_dict(),
            "unrun": result.unrun,
            "budget": result.budget,
            "inadmissible": result.inadmissible,
            "dollar_cap_usd": str(LIVE_DOLLAR_CAP),
            "calls": result.calls,
            "provider_attempts": len(result.attempts),
            "reported_cost_usd": None if result.reported_cost_usd is None else str(result.reported_cost_usd),
            "request_ids": list(result.request_ids),
        },
    )
    return 0 if passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    env = commands.add_parser("envelope", help="print the paid-call envelope; makes no call")
    env.add_argument("--registry", type=Path)
    env.add_argument("--override", type=Path)
    check = commands.add_parser("check", help="fact-check one saved summary")
    check.add_argument("--summary", type=Path, required=True)
    check.add_argument("--step", choices=("step1", "final"), required=True)
    check.add_argument("--finish-status", default="stop")
    live = commands.add_parser("run", help="PAID: qualify the reviewed profile through the operator-started host's Gateway")
    live.add_argument("--profile", choices=(LIVE_PROFILE,), required=True)
    live.add_argument("--host-pid", type=int, required=True)
    live.add_argument("--gateway-pid", type=int, required=True)
    live.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "run":
        recorded_on = datetime.now(UTC).date().isoformat()
        return run_live(out=args.out, host_pid=args.host_pid, gateway_pid=args.gateway_pid, environ=os.environ, recorded_on=recorded_on)
    fixture = load_fixture()
    if args.command == "envelope":
        if args.registry is None:
            with resources.as_file(resources.files("optimus_model_policy").joinpath("defaults.yaml")) as packaged:
                snapshot = load_registry(packaged, args.override)
        else:
            snapshot = load_registry(args.registry, args.override)
        print(json.dumps(paid_envelope(snapshot, fixture), indent=2))
        return 0
    facts = fixture.step1_facts if args.step == "step1" else fixture.final_facts
    report = evaluate_summary(args.summary.read_text(encoding="utf-8"), args.finish_status, facts, fixture.rules, history=fixture.history)
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
