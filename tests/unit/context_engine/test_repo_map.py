"""Plan 12.10 Task 3: the repository map is deterministic, bounded and built only from observed structure."""

from __future__ import annotations

from context_engine.repo_map import MapFile, build_repo_map, imports_of, rank


def _files() -> list[MapFile]:
    return [
        MapFile("pkg/core.py", (), ("Core", "Core.run")),
        MapFile("pkg/a.py", ("pkg.core",), ("a_function",)),
        MapFile("pkg/b.py", ("pkg.core", "pkg.a"), ("b_function",)),
        MapFile("isolated.py", ("os.path", "not.indexed"), ()),
    ]


def test_what_others_import_ranks_first() -> None:
    scores = rank(_files())
    assert scores["pkg/core.py"] > scores["pkg/a.py"] > scores["pkg/b.py"]
    assert abs(sum(scores.values()) - 1.0) < 1e-6


def test_an_import_outside_the_index_adds_no_edge() -> None:
    assert rank([MapFile("a.py", ("os.path",)), MapFile("b.py")]) == rank([MapFile("a.py"), MapFile("b.py")])


def test_an_ambiguous_module_name_adds_no_edge() -> None:
    files = [MapFile("x/util.py"), MapFile("y/util.py"), MapFile("z.py", ("util",))]
    scores = rank(files)
    assert scores["x/util.py"] == scores["y/util.py"]


def test_the_map_names_files_and_symbols_in_rank_order() -> None:
    result = build_repo_map(_files(), budget_chars=1000)
    assert result.text.splitlines()[0] == "pkg/core.py: Core, Core.run"
    assert result.files_included == 4 and not result.truncated


def test_named_files_come_first() -> None:
    assert build_repo_map(_files(), budget_chars=1000, focus=["isolated.py"]).text.splitlines()[0] == "isolated.py"


def test_a_smaller_budget_is_a_prefix_of_the_same_order() -> None:
    whole = build_repo_map(_files(), budget_chars=1000).text
    small = build_repo_map(_files(), budget_chars=40)
    assert whole.startswith(small.text) and small.truncated and len(small.text) <= 40


def test_the_map_is_deterministic_whatever_the_input_order() -> None:
    assert build_repo_map(_files(), budget_chars=1000) == build_repo_map(list(reversed(_files())), budget_chars=1000)


def test_a_file_that_does_not_fit_is_left_out_whole() -> None:
    assert build_repo_map([MapFile("long.py", (), ("x" * 100,))], budget_chars=10).text == ""


def test_imports_are_read_from_the_description() -> None:
    assert imports_of("imports: a.b c") == ("a.b", "c")
    assert imports_of(None) == () and imports_of("class Foo") == ()
