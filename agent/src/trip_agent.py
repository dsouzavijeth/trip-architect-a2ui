"""Trip Architect agent.

FIXED-schema pattern: typed Python tools build the A2UI surfaces and emit ops.
`propose_stop` renders one StopCard per turn; `finish_trip` renders a completion
card (with Plan more / Start over) so the trip has a real "done" state instead of
trailing chat text. Open models are far more reliable calling typed tools than
authoring raw A2UI, and there is no forced tool_choice anywhere on this route.
"""
from __future__ import annotations

from uuid import uuid4

from copilotkit import CopilotKitMiddleware, a2ui
from langchain.agents import create_agent
from langchain.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from src.catalog import CATALOG_ID
from src.llm import get_model

CATEGORIES = ["sight", "food", "stay", "nature", "culture", "nightlife"]


def build_stop_card(stop: dict) -> list[dict]:
    """A flat A2UI tree for one stop proposal (catalog components, all inline)."""
    approve_ctx = {
        "id": stop["id"],
        "name": stop["name"],
        "lat": stop["lat"],
        "lng": stop["lng"],
        "category": stop["category"],
        "note": stop["note"],
        "time": stop.get("time", ""),
    }
    return [
        {"id": "root", "component": "Card", "tone": "default", "child": "stack"},
        {
            "id": "stack",
            "component": "Stack",
            "gap": "sm",
            "children": ["ov", "hd", "note", "meta", "actions"],
        },
        {"id": "ov", "component": "Overline", "text": stop["category"].upper()},
        {"id": "hd", "component": "Heading", "level": "2", "text": stop["name"]},
        {"id": "note", "component": "Text", "tone": "muted", "text": stop["note"]},
        {
            "id": "meta",
            "component": "Badge",
            "label": stop.get("time") or "Suggested stop",
            "tone": "neutral",
        },
        {
            "id": "actions",
            "component": "Row",
            "gap": "sm",
            "justify": "start",
            "children": ["approve", "skip"],
        },
        {
            "id": "approve",
            "component": "Button",
            "label": "Add to trip",
            "variant": "primary",
            "action": {"event": {"name": "approve_stop", "context": approve_ctx}},
        },
        {
            "id": "skip",
            "component": "Button",
            "label": "Skip",
            "variant": "ghost",
            "action": {
                "event": {
                    "name": "skip_stop",
                    "context": {"id": stop["id"], "name": stop["name"]},
                }
            },
        },
    ]


def build_complete_card(summary: str) -> list[dict]:
    """The completion surface: a summary plus Plan more / Start over."""
    return [
        {"id": "root", "component": "Card", "tone": "mint", "child": "stack"},
        {
            "id": "stack",
            "component": "Stack",
            "gap": "sm",
            "children": ["ov", "hd", "sum", "actions"],
        },
        {"id": "ov", "component": "Overline", "text": "TRIP READY"},
        {"id": "hd", "component": "Heading", "level": "2", "text": "Your itinerary is set"},
        {"id": "sum", "component": "Text", "tone": "muted", "text": summary},
        {
            "id": "actions",
            "component": "Row",
            "gap": "sm",
            "justify": "start",
            "children": ["more", "restart"],
        },
        {
            "id": "more",
            "component": "Button",
            "label": "Plan more",
            "variant": "secondary",
            "action": {"event": {"name": "plan_more", "context": {}}},
        },
        {
            "id": "restart",
            "component": "Button",
            "label": "Start over",
            "variant": "ghost",
            "action": {"event": {"name": "restart_trip", "context": {}}},
        },
    ]


@tool
def propose_stop(
    name: str,
    lat: float,
    lng: float,
    category: str,
    note: str,
    time: str = "",
) -> str:
    """Propose the single next stop and render it as a card. Call ONCE per turn.

    Args:
        name: Real name of the place.
        lat: Latitude (accurate for the named place).
        lng: Longitude (accurate for the named place).
        category: sight | food | stay | nature | culture | nightlife.
        note: One sentence on why it's worth it.
        time: When to go, e.g. "Day 1 · Morning". Optional.
    """
    stop = {
        "id": uuid4().hex[:8],
        "name": name,
        "lat": lat,
        "lng": lng,
        "category": category if category in CATEGORIES else "sight",
        "note": note,
        "time": time,
    }
    surface = f"stop-{stop['id']}"
    return a2ui.render(
        operations=[
            a2ui.create_surface(surface, catalog_id=CATALOG_ID),
            a2ui.update_components(surface, build_stop_card(stop)),
        ]
    )


@tool
def finish_trip(summary: str) -> str:
    """Close out the trip with a completion card. Call ONCE, instead of
    propose_stop, when the itinerary is complete or the traveller is done.

    Args:
        summary: A short 2-3 line recap of the trip's shape. Plain text.
    """
    surface = f"done-{uuid4().hex[:8]}"
    return a2ui.render(
        operations=[
            a2ui.create_surface(surface, catalog_id=CATALOG_ID),
            a2ui.update_components(surface, build_complete_card(summary)),
        ]
    )


SYSTEM_PROMPT = """\
You are "Atlas", a travel architect. You design trips collaboratively, ONE stop
at a time. You never dump a full itinerary at once.

## How a turn works

The traveller may:
  A) Describe a trip ("3 days in Lisbon, food-heavy, easy pace").
  B) Send feedback ("more local food", "skip the touristy stuff").
  C) Approve or skip a stop, or tap a completion button. The runtime delivers
     this as a tool result `log_a2ui_event`, e.g.:
        User performed action "approve_stop" on surface "stop-ab12cd".
        Context: {"name": "Time Out Market", "lat": 38.70, ...}
     Possible action names: approve_stop, skip_stop, plan_more, restart_trip.

## Your loop

1. Pick the single best NEXT stop given the destination, the trip so far, and the
   traveller's taste. Keep stops geographically sensible; group a day together.
2. Call `propose_stop(...)` ONCE with a real place and accurate coordinates.
3. STOP. Do not call any tool again this turn.

Reacting to events:
- approve_stop  -> acknowledge in ONE short sentence, then `propose_stop` the next.
- skip_stop     -> `propose_stop` a genuinely DIFFERENT place (never the same one).
- plan_more     -> `propose_stop` the next stop.
- restart_trip  -> the itinerary was cleared. Start fresh: propose a first stop
                   from the prior context, or ask one short question if unclear.

## Finishing

When you have covered what the traveller asked for (e.g. enough stops for the days
requested — usually 4-8 total), or they say they're done, call `finish_trip(summary=...)`
ONCE instead of propose_stop. Put the 2-3 line recap in the `summary` argument.
Do NOT write the summary as plain chat text — the completion card IS the recap.

## Hard rules

- Exactly ONE tool call per turn: `propose_stop` OR `finish_trip`. Never both, never twice.
- Never propose a place that already appears in an earlier approve_stop event — check
  the history first.
- Coordinates must be plausible for the named place. Never invent fake coordinates.
- Keep chat text to one short sentence — the card and the map carry the detail.
"""


def build_trip_agent():
    return create_agent(
        model=get_model(),
        tools=[propose_stop, finish_trip],
        middleware=[CopilotKitMiddleware()],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=MemorySaver(),
    )


graph = build_trip_agent()
