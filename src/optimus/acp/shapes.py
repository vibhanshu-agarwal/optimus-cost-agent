from __future__ import annotations

import uuid
from typing import Any


def text_content_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def tool_call_text_content(text: str) -> dict[str, Any]:
    return {"type": "content", "content": text_content_block(text)}


def plan_entries_from_text(plan_text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in plan_text.splitlines() if line.strip()]
    if not lines:
        return [{"content": plan_text, "priority": "medium", "status": "pending"}]
    return [{"content": line, "priority": "medium", "status": "pending"} for line in lines]


def build_plan_session_update(*, session_id: str, plan_text: str, entry_status: str = "pending") -> dict[str, Any]:
    entries = plan_entries_from_text(plan_text)
    if entry_status != "pending":
        entries = [{**entry, "status": entry_status} for entry in entries]
    return {
        "sessionId": session_id,
        "update": {
            "sessionUpdate": "plan",
            "entries": entries,
        },
    }


def build_agent_message_chunk_notification(*, session_id: str, text: str) -> dict[str, Any]:
    return {
        "sessionId": session_id,
        "update": {
            "sessionUpdate": "agent_message_chunk",
            "content": text_content_block(text),
        },
    }


def build_permission_tool_call(*, tool_call_id: str, plan_text: str) -> dict[str, Any]:
    return {
        "toolCallId": tool_call_id,
        "title": "Approve plan execution",
        "status": "pending",
        "kind": "edit",
        "content": [tool_call_text_content(plan_text)],
    }


def build_request_permission_params(
    *,
    session_id: str,
    tool_call_id: str,
    plan_text: str,
    plan_hash: str,
    run_id: str,
) -> dict[str, Any]:
    return {
        "sessionId": session_id,
        "toolCall": build_permission_tool_call(tool_call_id=tool_call_id, plan_text=plan_text),
        "options": [
            {
                "optionId": "approve",
                "name": "Approve",
                "kind": "allow_once",
                "metadata": {"planHash": plan_hash},
            },
            {
                "optionId": "cancel",
                "name": "Cancel",
                "kind": "reject_once",
                "metadata": {"planHash": plan_hash},
            },
        ],
        "_meta": {"runId": run_id, "planHash": plan_hash},
    }


def tool_kind_for_name(tool_name: str) -> str:
    return {
        "file_reader": "read",
        "write_file": "edit",
        "test_runner": "execute",
    }.get(tool_name, "other")


def build_tool_call_notification(
    *,
    session_id: str,
    tool_call_id: str,
    title: str,
    summary: str,
    kind: str,
    status: str = "completed",
) -> dict[str, Any]:
    return {
        "sessionId": session_id,
        "update": {
            "sessionUpdate": "tool_call",
            "toolCallId": tool_call_id,
            "title": title,
            "kind": kind,
            "status": status,
            "content": [tool_call_text_content(summary)],
        },
    }


def build_tool_call_update_notification(
    *,
    session_id: str,
    tool_call_id: str,
    title: str,
    summary: str,
    status: str = "completed",
) -> dict[str, Any]:
    return {
        "sessionId": session_id,
        "update": {
            "sessionUpdate": "tool_call_update",
            "toolCallId": tool_call_id,
            "title": title,
            "status": status,
            "content": [tool_call_text_content(summary)],
        },
    }


def new_tool_call_id() -> str:
    return f"tool-{uuid.uuid4().hex}"


def new_approval_id() -> str:
    return f"approval-{uuid.uuid4().hex}"
