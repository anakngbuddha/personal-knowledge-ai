"""4.2 The advisor, callable from chat.

Ask already has the retrieval and the map. What it did not have was the one move a
salesperson makes constantly: read a pile of customer requirements, then lay the product
list against it and say what is missing. That is not a search, and prompting the model to
do it from passages produces a plausible bundle rather than a checked one.

So it is a tool. The requirement text is read into a 4.1 brief, the 4.2 engine does the
matching and the graph checks deterministically, and the model receives the finished
recommendation as data to narrate, not a catalogue to guess from.

The returned payload is facts about the caller's own catalogue, so it is not fenced as
untrusted: none of it is document text. The document quotes it carries are already
truncated evidence strings that a person accepted onto the map.
"""

from __future__ import annotations

from typing import Any

from app.advisor.brief import extract_customer_brief
from app.advisor.service import build_recommendation
from app.tools.registry import ToolContext


def advisor_recommend_tool(ctx: ToolContext, requirements: str) -> dict[str, Any]:
    brief = extract_customer_brief(requirements)
    if brief.is_empty:
        return {
            "brief": brief.as_dict(),
            "recommendation": None,
            "note": (
                "No requirements could be read from that text. Ask the user what the "
                "customer needs: rooms, platforms, headcount, cloud, budget, timeline."
            ),
        }
    result = build_recommendation(
        ctx.db, principal=ctx.principal, workspace_id=ctx.workspace_id, brief=brief
    )
    payload = result.as_dict()
    return {
        "brief": brief.as_dict(),
        "recommendation": payload,
        "readable": result.as_markdown(),
        "product_count": payload["product_count"],
        "has_gaps": bool(payload["gaps"]),
    }
