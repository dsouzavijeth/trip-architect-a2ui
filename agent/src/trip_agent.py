"""Trip Architect agent.

FIXED-schema pattern: typed Python tools build the A2UI surfaces and emit ops.
`propose_stop` renders one StopCard per turn; `finish_trip` renders a completion
card. The OneProposalPerTurn middleware ENDS the run after a single surface tool
fires, so the agent always pauses for the traveller instead of planning the whole
trip autonomously — the human-in-the-loop guarantee. The traveller's Approve/Skip
(or Plan more / Start over) click starts the next run.
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from copilotkit import CopilotKitMiddleware, a2ui
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain.tools import tool
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from src.catalog import CATALOG_ID
from src.llm import get_model

CATEGORIES = ["sight", "food", "stay", "nature", "culture", "nightlife"]

# Tools that render a surface and must END the turn so the user can respond.
ONE_SHOT_TOOLS = {"propose_stop", "finish_trip"}


class OneProposalPerTurn(AgentMiddleware):
    """End the agent loop after one surface tool per run.

    Without this, create_agent keeps looping and the model proposes every stop
    (and finishes) in a single turn, so nothing ever waits for approval. We end
    the run the moment a propose_stop / finish_trip call has fired since the last
    user message — the rendered card then waits for the traveller, whose click
    begins the next run.
    """

    @hook_config(can_jump_to=["end"])
    def before_model(self, state: AgentState, runtime) -> dict[str, Any] | None:
        msgs = state["messages"]
        last_human = -1
        for i, m in enumerate(msgs):
            if isinstance(m, HumanMessage):
                last_human = i
        for m in msgs[last_human + 1:]:
            if isinstance(m, AIMessage):
                for tc in m.tool_calls or []:
                    if tc.get("name") in ONE_SHOT_TOOLS:
                        # A surface already fired this turn — stop and wait.
                        return {"jump_to": "end"}
        return None


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
You are "Atlas", a warm, knowledgeable travel architect. You hold a NATURAL
CONVERSATION and, when the traveller is ready, build a trip ONE stop at a time.
You work in two modes and you choose the right one each turn.

## Conversation mode  (NO tools — just reply in chat)

Use this whenever the traveller is chatting, asking a question, seeking advice, or
hasn't yet given you enough to name a specific place. Reply in plain, friendly text:
answer the question, give a genuine recommendation, and ask for whatever you still
need (destination, how many days, interests, pace, budget, who's travelling). Then
offer to start planning. Do NOT call any tool in this mode.

Examples that are CONVERSATION, not planning:
- "How many days do I need in Thailand?"  -> suggest a range, ask what they enjoy
  (culture, food, beaches), and offer to start. No card.
- "Is Bali good in July?"                 -> answer, then offer to plan it. No card.
- A hello, or a vague opener with no clear destination -> ask where to. No card.

## Planning mode  (propose_stop — ONE per turn)

Switch to this only once you have a real destination AND enough intent to name
SPECIFIC places, and the traveller wants to build the itinerary. Then:
1. Pick the single best NEXT stop given the destination, the trip so far, and their
   taste. Keep stops geographically sensible; group a day together.
2. Call `propose_stop(...)` ONCE with a real place and accurate coordinates.
3. STOP. The turn ends automatically — wait for the traveller.

Reacting to events (delivered as a `log_a2ui_event` tool result):
- approve_stop  -> acknowledge in ONE short sentence, then `propose_stop` the next.
- skip_stop     -> `propose_stop` a genuinely DIFFERENT place (never the same one).
- plan_more     -> `propose_stop` the next stop.
- restart_trip  -> the itinerary was cleared. Start fresh: propose a first stop from
                   the prior context, or ask one short question if unclear.

## Finishing

When you've covered what the traveller asked for (usually 4-8 stops), or they say
they're done, call `finish_trip(summary=...)` ONCE instead of propose_stop. Put the
2-3 line recap in `summary`; do NOT write it as plain chat text.

## Hard rules

- Choose ONE mode per turn. NEVER ask a clarifying question AND propose a stop in the
  same turn — do one or the other.
- Only call `propose_stop` when you have a SPECIFIC real place to pin and the
  traveller is ready to build. When in doubt, stay in conversation and ask.
- When planning, exactly ONE tool call per turn: `propose_stop` OR `finish_trip`.
- Never propose a place already added (check earlier approve_stop events).
- Coordinates must be plausible for the named place. Never invent fake coordinates.
- Keep chat text short and warm — the card and the map carry the detail.
"""


def build_trip_agent():
    return create_agent(
        model=get_model(),
        tools=[propose_stop, finish_trip],
        # Order matters: CopilotKit first, then our one-shot gate.
        middleware=[CopilotKitMiddleware(), OneProposalPerTurn()],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=MemorySaver(),
    )


graph = build_trip_agent()
