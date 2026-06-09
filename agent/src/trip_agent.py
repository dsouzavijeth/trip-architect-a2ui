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

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_UA = {"User-Agent": "atlas-trip-architect/1.0 (demo)"}
# Region lookups are constant across a trip, so cache them.
_region_cache: dict[str, dict | None] = {}


def _search(query: str, viewbox: str | None = None) -> dict | None:
    """One Nominatim hit (or None). When viewbox is set, results are confined to
    that box, so a venue can never resolve to the wrong city/continent."""
    params: dict = {"q": query, "format": "json", "limit": 1}
    if viewbox:
        params["viewbox"] = viewbox
        params["bounded"] = 1
    try:
        resp = httpx.get(NOMINATIM_URL, params=params, headers=_UA, timeout=8.0)
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else None
    except Exception:
        return None


def _region_info(region: str) -> dict | None:
    """Resolve the region to a centre point + bounding box (cached)."""
    region = (region or "").strip()
    if region in _region_cache:
        return _region_cache[region]
    hit = _search(region) if region else None
    info = None
    if hit:
        viewbox = None
        bb = hit.get("boundingbox")  # [min_lat, max_lat, min_lon, max_lon]
        if bb and len(bb) == 4:
            viewbox = f"{bb[2]},{bb[0]},{bb[3]},{bb[1]}"  # min_lon,min_lat,max_lon,max_lat
        info = {"center": (float(hit["lat"]), float(hit["lon"])), "viewbox": viewbox}
    _region_cache[region] = info
    return info


def geocode(name: str, region: str) -> tuple[float, float] | None:
    """Resolve a venue's real coordinates, CONFINED to its region.

    1. Resolve the region to a bounding box.
    2. Search the venue bounded to that box (so "Theobroma, Bangalore" can't
       match a town in Brazil).
    3. If the venue isn't in OpenStreetMap, fall back to the region centre — the
       right city, not the wrong continent.
    Returns None only if the region itself can't be resolved (caller then uses the
    model's guessed coords). For pin-perfect accuracy, swap in a keyed geocoder
    (Google / Mapbox) here.
    """
    info = _region_info(region)
    if info:
        if name.strip():
            hit = _search(f"{name}, {region}".strip().strip(","), viewbox=info["viewbox"])
            if hit:
                return float(hit["lat"]), float(hit["lon"])
        return info["center"]
    # Region unknown: one last unbounded attempt, else give up.
    hit = _search(f"{name}, {region}".strip().strip(","))
    if hit:
        return float(hit["lat"]), float(hit["lon"])
    return None

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
            "label": "Add another stop",
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
    region: str,
    lat: float,
    lng: float,
    category: str,
    note: str,
    time: str = "",
) -> str:
    """Propose the single next stop and render it as a card. Call ONCE per turn.

    Coordinates are resolved from the place name automatically (geocoding), so the
    map pins the real spot. Always pass `region`; still give your best lat/lng as a
    fallback for places the geocoder can't find.

    Args:
        name: Real name of the place (e.g. "Tanjung Rhu Beach").
        region: The destination/area for accurate lookup (e.g. "Langkawi, Malaysia").
        lat: Best-guess latitude (fallback only).
        lng: Best-guess longitude (fallback only).
        category: sight | food | stay | nature | culture | nightlife.
        note: One sentence on why it's worth it.
        time: When to go, e.g. "Day 1 · Morning". Optional.
    """
    # Trust the geocoder over the model's numbers; fall back through name, then the
    # region centre (keeps the pin on land), then the model's own lat/lng.
    resolved = geocode(name, region)
    final_lat, final_lng = resolved if resolved else (lat, lng)

    stop = {
        "id": uuid4().hex[:8],
        "name": name,
        "lat": final_lat,
        "lng": final_lng,
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
2. Call `propose_stop(...)` ONCE with a real place and its `region` (e.g.
   "Langkawi, Malaysia"). Exact coordinates are resolved automatically from the
   name; still pass your best-guess lat/lng as a fallback.
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
- Always pass `region` (the destination/area). Coordinates are geocoded from the
  name, so name the place precisely; your lat/lng is only a fallback.
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
