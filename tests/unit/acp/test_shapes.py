from optimus.acp.shapes import (
    build_agent_message_chunk_notification,
    build_permission_tool_call,
    build_plan_session_update,
    build_request_permission_params,
    build_tool_call_notification,
    build_tool_call_update_notification,
    plan_entries_from_text,
)


def test_plan_entry_content_is_plain_string_not_content_blocks():
    entries = plan_entries_from_text("READ README.md\nWRITE example.py")
    assert entries == [
        {"content": "READ README.md", "priority": "medium", "status": "pending"},
        {"content": "WRITE example.py", "priority": "medium", "status": "pending"},
    ]
    for entry in entries:
        assert isinstance(entry["content"], str)


def test_build_plan_session_update_matches_acp_v1_shape():
    payload = build_plan_session_update(session_id="sess-1", plan_text="WRITE example.py")
    assert payload == {
        "sessionId": "sess-1",
        "update": {
            "sessionUpdate": "plan",
            "entries": [
                {"content": "WRITE example.py", "priority": "medium", "status": "pending"},
            ],
        },
    }


def test_build_agent_message_chunk_notification_matches_acp_v1_shape():
    payload = build_agent_message_chunk_notification(session_id="sess-1", text="Done.")
    assert payload == {
        "sessionId": "sess-1",
        "update": {
            "sessionUpdate": "agent_message_chunk",
            "content": {"type": "text", "text": "Done."},
        },
    }


def test_build_request_permission_params_nests_tool_call_update():
    params = build_request_permission_params(
        session_id="sess-1",
        tool_call_id="tool-abc",
        plan_text="WRITE example.py",
        plan_hash="hash-1",
        run_id="sess-1:2",
    )
    assert set(params.keys()) == {"sessionId", "toolCall", "options", "_meta"}
    assert params["toolCall"] == build_permission_tool_call(tool_call_id="tool-abc", plan_text="WRITE example.py")
    assert params["toolCall"]["toolCallId"] == "tool-abc"
    assert "toolCallId" not in params


def test_build_tool_call_notification_flattens_fields_at_update_level():
    payload = build_tool_call_notification(
        session_id="sess-1",
        tool_call_id="tool-abc",
        title="file_reader",
        summary="read README.md",
        kind="read",
    )
    update = payload["update"]
    assert update["sessionUpdate"] == "tool_call"
    assert update["toolCallId"] == "tool-abc"
    assert update["title"] == "file_reader"
    assert update["kind"] == "read"
    assert update["status"] == "completed"
    assert update["content"] == [
        {"type": "content", "content": {"type": "text", "text": "read README.md"}},
    ]
    assert "toolCall" not in update


def test_build_tool_call_update_flattens_fields_at_update_level():
    payload = build_tool_call_update_notification(
        session_id="sess-1",
        tool_call_id="tool-abc",
        title="write_file",
        summary="wrote example.py",
    )
    update = payload["update"]
    assert update["sessionUpdate"] == "tool_call_update"
    assert update["toolCallId"] == "tool-abc"
    assert update["title"] == "write_file"
    assert update["content"] == [
        {"type": "content", "content": {"type": "text", "text": "wrote example.py"}},
    ]
    assert "toolCall" not in update
