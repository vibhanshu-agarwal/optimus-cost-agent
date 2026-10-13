"""The hosted work-status table: the Pages workflow publishes only the page, only from main, with least privilege, and the documents link to the hosted address."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "work-status-pages.yml"
PAGE = REPO_ROOT / "docs" / "work-status.html"
LINKING_DOCUMENTS = (
    "README.md",
    "docs/README.md",
    "AGENTS.md",
    "docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md",
)


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _page_repo() -> str:
    block = re.search(r'<script type="application/json" id="work-status-vocabulary">.*?"repo": "(?P<repo>[^"]+)"', PAGE.read_text(encoding="utf-8"), re.DOTALL)
    assert block is not None
    return block["repo"]


def _hosted_url() -> str:
    owner, name = _page_repo().split("/")
    return f"https://{owner.lower()}.github.io/{name}/work-status.html"


def test_pages_workflow_runs_only_after_a_merge_and_never_on_a_pull_request() -> None:
    text = _workflow()
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert re.search(r"^on:\n  push:\n    branches: \[main\]\n    paths:\n", code, re.MULTILINE)
    assert "  workflow_dispatch:" in code
    assert "pull_request" not in code


def test_pages_workflow_deploys_only_from_main_even_when_started_by_hand() -> None:
    code = _workflow()
    job = code.split("\njobs:\n", 1)[1]
    assert job.startswith("  deploy:\n    if: github.ref == 'refs/heads/main'\n    runs-on: ubuntu-latest\n")
    assert job.count("    if: ") == 1


def test_pages_workflow_has_least_privilege_and_no_secret() -> None:
    code = _workflow()
    assert re.search(r"^permissions:\n  contents: read\n", code, re.MULTILINE)
    job = code.split("\njobs:\n", 1)[1]
    assert re.search(r"    permissions:\n      contents: read\n      pages: write\n      id-token: write\n", job)
    assert job.count("write") == 2  # pages and id-token only
    assert "secrets." not in code and "GITHUB_TOKEN" not in code


def test_pages_workflow_publishes_the_page_and_a_redirect_only() -> None:
    code = _workflow()
    assert code.count("cp docs/work-status.html _site/work-status.html") == 1
    assert len(re.findall(r"^\s+(?:cp|mv|rsync|mkdir -p)\b", code, re.MULTILINE)) == 1
    assert "          path: _site\n" in code
    assert "uses: actions/upload-pages-artifact@v5" in code and "uses: actions/deploy-pages@v5" in code


def test_the_hosted_address_matches_the_pages_repository_and_every_listed_document_links_it() -> None:
    hosted = _hosted_url()
    assert hosted == "https://vibhanshu-agarwal.github.io/optimus-cost-agent/work-status.html"
    for relative in LINKING_DOCUMENTS:
        assert hosted in (REPO_ROOT / relative).read_text(encoding="utf-8"), relative


def test_the_docs_index_row_leads_with_the_hosted_table_and_keeps_a_relative_source_link() -> None:
    index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "| [Work status table][work-status-hosted] |" in index
    assert f"\n[work-status-hosted]: {_hosted_url()}\n" in index
    assert "[`work-status.html`](work-status.html)" in index  # the source stays indexed by a relative link
    # The docs-index test counts every inline [text](url) target as a repository path, so the hosted address must not be an inline link here.
    assert f"]({_hosted_url()})" not in index
    assert "Live work status" in (REPO_ROOT / "README.md").read_text(encoding="utf-8")
