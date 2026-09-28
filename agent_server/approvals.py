"""Translating LangGraph interrupts to and from the Responses API approval items.

`HumanInTheLoopMiddleware` pauses a run and expects `{"decisions": [...]}` back.
The chat client speaks the OpenAI Responses MCP protocol instead: it reads
`mcp_approval_request` items out of the output and replays the whole history with
an `mcp_approval_response` attached. This module is the adapter between them.

The client is stateless and replays; LangGraph is stateful and resumes. The two
are reconciled by `thread_id`, so a resumed run continues the paused graph rather
than replaying the conversation through it.
"""

from __future__ import annotations

import json
from typing import Any

SERVER_LABEL = "dbsql"


def approval_requests(interrupt: Any) -> list[dict]:
    """The `mcp_approval_request` items for one paused run.

    One per tool call, because the model batches them and the client approves
    each separately. The id is positional — `<interrupt id>:<n>` — since the
    resume must line decisions up with `action_requests` in order.
    """
    value = getattr(interrupt, "value", interrupt) or {}
    base = getattr(interrupt, "id", "approval")
    return [
        {
            "type": "mcp_approval_request",
            "id": f"{base}:{n}",
            "name": request.get("name", ""),
            "arguments": json.dumps(request.get("args", {})),
            "server_label": SERVER_LABEL,
        }
        for n, request in enumerate(value.get("action_requests", []))
    ]


def decisions_from(items: list[dict]) -> list[dict] | None:
    """The `{"decisions": [...]}` payload for a resume, or None if this is not one.

    Ordered by the positional suffix rather than by arrival, because the client
    replays history and nothing guarantees the order it sends them in.
    """
    responses = [i for i in items if i.get("type") == "mcp_approval_response"]
    if not responses:
        return None

    def position(item: dict) -> int:
        ident = str(item.get("approval_request_id", ""))
        _, _, suffix = ident.rpartition(":")
        return int(suffix) if suffix.isdigit() else 0

    return [
        {"type": "approve" if r.get("approve") else "reject"}
        for r in sorted(responses, key=position)
    ]
