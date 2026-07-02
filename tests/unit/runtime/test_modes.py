from optimus.runtime.modes import (
    ExecutionMode,
    GenerationScope,
    classify_generation_scope,
)


def test_execution_mode_values_match_public_contract():
    assert ExecutionMode.PLAN.value == "PLAN"
    assert ExecutionMode.CHAT.value == "CHAT"
    assert ExecutionMode.AGENT.value == "AGENT"


def test_inline_snippet_scope_for_short_advisory_text():
    scope = classify_generation_scope(
        generated_line_count=14,
        modified_paths=[],
        created_paths=[],
        deleted_paths=[],
        touches_core_package=False,
    )

    assert scope is GenerationScope.INLINE_SNIPPET


def test_patch_proposal_scope_for_existing_file_patch_text():
    scope = classify_generation_scope(
        generated_line_count=30,
        modified_paths=["src/optimus/acp/dispatcher.py"],
        created_paths=[],
        deleted_paths=[],
        touches_core_package=False,
    )

    assert scope is GenerationScope.PATCH_PROPOSAL


def test_file_mutation_scope_for_single_file_create_or_delete():
    create_scope = classify_generation_scope(
        generated_line_count=5,
        modified_paths=[],
        created_paths=["src/optimus/runtime/state.py"],
        deleted_paths=[],
        touches_core_package=False,
    )
    delete_scope = classify_generation_scope(
        generated_line_count=5,
        modified_paths=[],
        created_paths=[],
        deleted_paths=["src/optimus/runtime/state.py"],
        touches_core_package=False,
    )

    assert create_scope is GenerationScope.FILE_MUTATION
    assert delete_scope is GenerationScope.FILE_MUTATION


def test_multi_file_changeset_scope_for_core_or_multiple_roots():
    core_scope = classify_generation_scope(
        generated_line_count=5,
        modified_paths=["src/optimus/runtime/state.py"],
        created_paths=[],
        deleted_paths=[],
        touches_core_package=True,
    )
    roots_scope = classify_generation_scope(
        generated_line_count=5,
        modified_paths=["src/optimus/runtime/state.py", "tests/unit/runtime/test_state.py"],
        created_paths=[],
        deleted_paths=[],
        touches_core_package=False,
    )

    assert core_scope is GenerationScope.MULTI_FILE_CHANGESET
    assert roots_scope is GenerationScope.MULTI_FILE_CHANGESET
