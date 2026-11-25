from pathlib import Path
from textwrap import dedent

import pytest

from tools.verify_acp_instrumentation import CoverageError, audit_instrumentation, classify_source

ROOT = Path(__file__).resolve().parents[3]
WRITER = "optimus.acp.outbound_writer"


def test_current_owners_have_every_selected_callable_classified():
    coverage = audit_instrumentation(ROOT)
    assert coverage["optimus.acp.dispatcher:JsonRpcDispatcher.dispatch"].kind == "EXPLICIT_BODY"
    assert coverage["optimus.acp.server:AcpStreamServer._serve_ndjson.owned_request"].kind == "EXPLICIT_BODY"
    assert coverage["optimus.mcp.client_sdk:ClientMcpSdkAdapter.call"].kind == "INSTRUMENTED"
    excluded = coverage["optimus.acp.outbound_writer:DedicatedOutboundWriter.submit"]
    assert excluded.kind == "EXCLUDED" and excluded.reason


def test_new_method_in_an_owned_class_is_rejected():
    source = (ROOT / "src/optimus/acp/outbound_writer.py").read_text(encoding="utf-8")
    anchor = "    @observe_operation\n    def start(self)"
    assert source.count(anchor) == 1
    source = source.replace(anchor, "    def newly_added(self):\n        return None\n\n" + anchor)
    with pytest.raises(CoverageError, match=r"unclassified.*DedicatedOutboundWriter\.newly_added"):
        classify_source(WRITER, source)


@pytest.mark.parametrize(
    "imports,stack",
    [
        ("from other import observe_operation as observe", "@observe"),
        ("import optimus.acp.debug_trace as trace\ntrace.observe_operation = lambda f: f", "@trace.observe_operation"),
        ("from optimus.acp.debug_trace import observe_operation as observe\nobserve = lambda f: f", "@observe"),
        ("from optimus.acp.debug_trace import observe_operation as observe", "@observe\n@staticmethod"),
        ("from optimus.acp.debug_trace import observe_operation as observe", "@staticmethod()\n@observe"),
        ("from optimus.acp.debug_trace import observe_operation as observe\nfrom functools import cache", "@cache\n@observe"),
        ("from optimus.acp.debug_trace import observe_operation as observe", "@observe\n@observe"),
    ],
)
def test_decorator_identity_and_order_are_enforced(imports, stack):
    source = imports + "\nclass DedicatedOutboundWriter:\n"
    source += "".join(f"    {line}\n" for line in stack.splitlines())
    source += "    def start(self):\n        return None\n"
    with pytest.raises(CoverageError, match=r"DedicatedOutboundWriter\.start"):
        classify_source(WRITER, source)


def test_exact_alias_with_outer_descriptor_and_inner_cache_is_recognized():
    source = dedent("""\
        import optimus.acp.debug_trace as trace
        from builtins import staticmethod as static
        from functools import lru_cache as memo

        class DedicatedOutboundWriter:
            @static
            @trace.observe_operation
            @memo(maxsize=4)
            def start(value):
                return value
        """)
    assert classify_source(WRITER, source)["optimus.acp.outbound_writer:DedicatedOutboundWriter.start"].kind == "INSTRUMENTED"


def test_nominal_body_match_cannot_replace_the_explicit_request_scope():
    source = dedent("""\
        from another import observe_request

        class JsonRpcDispatcher:
            def dispatch(self, request):
                with observe_request(request):
                    return None
        """)
    with pytest.raises(CoverageError, match=r"explicit scope.*JsonRpcDispatcher\.dispatch"):
        classify_source("optimus.acp.dispatcher", source)


def test_an_import_after_the_class_cannot_authorize_a_decorator():
    source = dedent("""\
        from another import observe_operation as observe

        class DedicatedOutboundWriter:
            @observe
            def start(self):
                return None

        from optimus.acp.debug_trace import observe_operation as observe
        """)
    with pytest.raises(CoverageError, match=r"DedicatedOutboundWriter\.start"):
        classify_source(WRITER, source)


@pytest.mark.parametrize(
    "inside,outside",
    [
        ("    start = lambda self: None\n", ""),
        ("    start = start.__wrapped__\n", ""),
        ("    del start\n", ""),
        ("", "DedicatedOutboundWriter.start = lambda self: None\n"),
        ("", "setattr(DedicatedOutboundWriter, 'start', lambda self: None)\n"),
        ("", "delattr(DedicatedOutboundWriter, 'start')\n"),
    ],
)
def test_runtime_replacement_cannot_keep_a_callable_classified(inside, outside):
    source = dedent("""\
        from optimus.acp.debug_trace import observe_operation

        class DedicatedOutboundWriter:
            @observe_operation
            def start(self):
                return None
        """) + inside + outside
    with pytest.raises(CoverageError, match=r"rebound.*DedicatedOutboundWriter\.start"):
        classify_source(WRITER, source)


def test_async_cache_stack_is_rejected():
    source = dedent("""\
        from functools import cache
        from optimus.acp.debug_trace import observe_operation

        class DedicatedOutboundWriter:
            @observe_operation
            @cache
            async def start(self):
                return None
        """)
    with pytest.raises(CoverageError, match=r"invalid.*DedicatedOutboundWriter\.start"):
        classify_source(WRITER, source)
