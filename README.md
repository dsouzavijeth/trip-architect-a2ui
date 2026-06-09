# Atlas — an Agentic Trip Architect (A2UI + Nebius)

Atlas plans a trip **one stop at a time**. You describe where you're going; an
open-source LLM proposes the next stop and **renders it as a card it composes
itself** — name, why, when, and Approve / Skip buttons. Approve, and the stop pins
to a live map and Atlas proposes the next one. When the itinerary is done, you get a
completion card instead of more suggestions.

The point of the project: the agent doesn't just answer in text and leave you to
build the UI — it **generates the interface** from a catalog of components you own,
using Google's **A2UI** protocol, while a human approves every move. And it does
this on an **open-weights model** served by Nebius Token Factory, not a frontier
closed model.

> **Based on** CopilotKit's official A2UI showcase, the **A2UI PDF Analyst**:
> <https://github.com/CopilotKit/CopilotKit/tree/main/examples/showcases/a2ui-pdf-analyst>
> This project reuses that example's A2UI plumbing (the catalog + renderer system,
> the surface bus, the mirror activity renderer, and the `HttpAgent` → Python
> bridge) and adapts it from "chat with a PDF" to "plan a trip", swaps the runtime
> model to an open model on Nebius, and adds the map + approval loop. Full credit to
> the CopilotKit team for the original. See [Acknowledgements](#acknowledgements).

---

## Table of contents

- [Atlas — an Agentic Trip Architect (A2UI + Nebius)](#atlas--an-agentic-trip-architect-a2ui--nebius)
  - [Table of contents](#table-of-contents)
  - [What it does](#what-it-does)
  - [Architecture](#architecture)
  - [How a turn works (the full loop)](#how-a-turn-works-the-full-loop)
  - [Tech stack](#tech-stack)
  - [Prerequisites](#prerequisites)
  - [Setup \& run](#setup--run)
  - [Configuration: the model](#configuration-the-model)
  - [Project structure](#project-structure)
    - [The key files, in one line each](#the-key-files-in-one-line-each)
  - [The A2UI catalog](#the-a2ui-catalog)
  - [Customizing](#customizing)
  - [Acknowledgements](#acknowledgements)
    - [License](#license)

---

## What it does

- You chat on the left; a map and the current proposal sit on the right.
- **Ask first, plan when ready.** Atlas holds a normal conversation — ask "how many
  days do I need in Thailand?" and it just answers. It only starts proposing stops
  once you have a destination and want to build the itinerary.
- Atlas proposes **one** real place per turn as an A2UI **StopCard** (category,
  name, one-line reason, suggested time, Approve / Skip).
- **Add to trip** drops a numbered pin at the place's real, geocoded location, draws
  the route line between stops, and Atlas proposes the next.
- **Skip** asks Atlas for a genuinely different place.
- **Hover a pin** for that stop's details, and a collapsible **"Your plan"** panel
  overlays the map with the full itinerary, grouped by day.
- You can steer at any time ("more local food", "skip the touristy stuff") and the
  next card reacts.
- When the trip is complete (or you say you're done), Atlas renders a **completion
  card** with a short recap and **Add another stop** / **Start over** — no more
  suggestions until you ask.

---

## Architecture

Three layers, cleanly separated:

| Layer | What it is | Where |
|-------|------------|-------|
| **A2UI** (Agent-to-UI) | Google's open protocol. The agent describes a UI *surface* as structured component operations (`createSurface`, `updateComponents`, `updateDataModel`) that the frontend renders against its **own** component catalog. | emitted by the Python agent |
| **AG-UI** | CopilotKit's transport. Carries A2UI operations to the browser and user actions back to the agent over HTTP/SSE. | `@copilotkit/*` |
| **The agent** | A LangGraph agent (`create_agent`) wrapped by the `copilotkit` Python SDK, served over AG-UI by FastAPI. Runs an **open model on Nebius Token Factory** via `langchain-openai`. | `agent/` (Python) |

```
 Browser (Next.js)
 ┌────────────────────────────────────────────────────────────┐
 │  /trip page                                                │
 │  ┌─────────────┐   ┌──────────────────────────────────────┐│
 │  │ CopilotChat │   │ TripWorkspace                        ││
 │  │ (left)      │   │  • Leaflet map (app-owned)           ││
 │  │             │   │  • current StopCard surface (A2UI)   ││
 │  └─────────────┘   └──────────────────────────────────────┘│
 └───────────────┬─────────────────────────────▲──────────────┘
                 │ POST /api/copilotkit        │ A2UI ops mirrored
                 ▼ (CopilotRuntime + HttpAgent)│ to the canvas
        ┌────────────────────────────────────────────────┐
        │ Next.js API route (bridge, runtime/v2)           │
        │  a2ui: { injectA2UITool: false }                 │
        └───────────────┬──────────────────────────────────┘
                        │ AG-UI over HTTP/SSE
                        ▼
        ┌────────────────────────────────────────────────┐
        │ Python FastAPI :8123  ──  /trip                │
        │  LangGraph create_agent + CopilotKit middleware│
        │  + OneProposalPerTurn (ends turn after 1 card) │
        │  tools: propose_stop, finish_trip              │
        │  coords geocoded via OpenStreetMap / Nominatim │
        │  model: Nebius open LLM (langchain-openai)     │
        │  emits A2UI ops via copilotkit.a2ui helpers    │
        └────────────────────────────────────────────────┘
```

**Why a Python agent?** This is the A2UI pattern from the upstream example: the
agent emits A2UI operations as *tool results*, and CopilotKit's A2UI middleware
turns any tool result containing `a2ui_operations` into rendered surfaces. The
Next.js side is a thin bridge — `CopilotRuntime` wrapping an `HttpAgent` that proxies
to the Python endpoint. There is no TypeScript agent.

**Why the map isn't A2UI.** A2UI shines for cards, forms, tables, and charts the
agent composes. The map is a different beast — it's an app-owned Leaflet canvas that
*consumes* approvals. The StopCard is A2UI; the map is plain React fed by approvals.

---

## How a turn works (the full loop)

**Conversation vs planning.** Not every turn renders a card. If you ask a question or
haven't settled on a destination, Atlas just replies in chat. Once you're ready to
build, it switches to the loop below.

1. **You ask** ("Plan me 3 days in Lisbon, food-heavy, easy pace"). The message goes
   through the bridge to the Python `trip_agent`.
2. **The agent calls `propose_stop(name, region, lat, lng, category, note, time)`** — a
   typed tool. The real coordinates are resolved by **geocoding the place within its
   region** (OpenStreetMap/Nominatim), so the pin lands correctly; the model's lat/lng is
   only a fallback. It builds a StopCard component tree (from the shared catalog) and
   returns A2UI ops: `create_surface` + `update_components`. The **Approve button inlines
   the full stop into its action context**.
3. **The surface streams to the browser.** The agent's tool result carries
   `a2ui_operations`; the A2UI middleware emits an activity message; `MirrorRenderer`
   forwards the ops onto the `surface-bus`; `TripWorkspace`'s canvas renders the
   StopCard. A small "surface → rendered in the canvas" pill is left in chat.
4. **You click Add to trip.** The catalog's Button renderer dispatches its
   `action.event`; `A2UIProvider`'s `onAction` receives it as
   `userAction = { name: "approve_stop", surfaceId, context: { …the stop } }`.
5. **`TripWorkspace.onAction`** does two things:
   - reads `userAction.context` and pushes the stop into the **`tripStore`** → the
     map pins it and extends the route;
   - re-runs the agent with `forwardedProps: { a2uiAction }`, so CopilotKit's A2UI
     middleware injects a `log_a2ui_event` tool result on the next run.
   It also immediately "consumes" the current card (replaces it with an "Atlas is
   thinking…" state) so it can't linger or be double-clicked.
6. **The agent sees the approval** (`log_a2ui_event`), acknowledges in one line, and
   calls `propose_stop` for the next place — back to step 2.
7. **When the trip is complete**, the agent calls **`finish_trip(summary)`** instead,
   which renders the completion card (**Add another stop** / **Start over**). Those
   buttons fire `plan_more` / `restart_trip` events through the same `onAction` path;
   `restart_trip` clears the map.

`skip_stop` works like `approve_stop` minus the pin: the agent proposes a different
place.

**The pause is enforced, not requested.** A small `OneProposalPerTurn` middleware ends
the agent's run the moment one `propose_stop` / `finish_trip` fires, so the loop always
waits for your click — even with a strong, eager model that would otherwise plan the
whole trip in a single turn.

---

## Tech stack

| Part | Stack |
|------|-------|
| Frontend | Next.js 16 · React 19 · Tailwind v4 · TypeScript · `@copilotkit/react-core/v2` · `@copilotkit/a2ui-renderer` · `react-leaflet` v5 + Leaflet · Recharts (catalog charts) |
| Bridge | `@copilotkit/runtime/v2` · `@ag-ui/client` (`HttpAgent`) · `@ag-ui/core` |
| Backend | Python 3.12 · FastAPI · `ag-ui-langgraph` · `copilotkit` (Python SDK) · LangChain + LangGraph · `langchain-openai` · OpenStreetMap / Nominatim geocoding |
| Model | Open LLM via **Nebius Token Factory** (OpenAI-compatible) |

---

## Prerequisites

- **Node.js 20+** and **pnpm** (npm works too)
- **Python 3.12**
- **[uv](https://docs.astral.sh/uv/)** for the Python agent (`pip install uv` is fine)
- A **Nebius Token Factory** API key — <https://tokenfactory.nebius.com/> → Settings → API keys

---

## Setup & run

```bash
# 1. install (also runs `uv sync` for the agent via postinstall)
pnpm install

# 2. add your key
cp agent/.env.example agent/.env
#    edit agent/.env:  NEBIUS_API_KEY=...

# 3. run web (:3000) + agent (:8123) together
pnpm dev
```

On Windows PowerShell, use `copy agent\.env.example agent\.env`. `npm install && npm run dev` works identically.

Open <http://localhost:3000> — it redirects to **`/trip`**. Type:

> Plan me 3 days in Lisbon, food-heavy, easy pace.

Quick health check: <http://localhost:8123/> returns
`{"ok": true, "agents": {"trip_agent": "/trip/"}}`.

---

## Configuration: the model

The model is configured once, on the Python side, in **`agent/src/llm.py`**. Nebius is
OpenAI-compatible, so it's a `ChatOpenAI` with the base URL and key overridden:

```python
ChatOpenAI(
    model=os.environ.get("NEBIUS_MODEL", "Qwen/Qwen2.5-72B-Instruct"),
    base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1"),
    api_key=os.environ["NEBIUS_API_KEY"],
    temperature=0,
)
```

Override the model without touching code via `agent/.env`:

```
NEBIUS_API_KEY=...
NEBIUS_MODEL=Qwen/Qwen2.5-72B-Instruct
# NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1
```

**Model choice matters.** The whole loop depends on the model reliably **calling
tools** (`propose_stop`, `finish_trip`). Pick a strong instruct model with solid
function-calling — e.g. `Qwen/Qwen2.5-72B-Instruct`, `meta-llama/Llama-3.3-70B-Instruct`,
`deepseek-ai/DeepSeek-V3`, or a large Nemotron. Confirm exact IDs in the Token Factory
playground (the catalog changes). A `-fast` variant, where offered, keeps the
propose→approve loop snappy. Small/omni models tend to be slow and unreliable at
tool-calling — the symptom is the agent replying in prose instead of rendering a card.

Coordinates aren't the model's job: it supplies the place name and `region`, and the
agent geocodes the real location (see [Customizing](#customizing) to swap in a keyed
geocoder for venue-precise pins).

---

## Project structure

```
agent/                                  # Python AG-UI agent
├── main.py                             # FastAPI app; registers /trip
├── pyproject.toml                      # uv-managed deps
├── .env.example                        # NEBIUS_API_KEY (+ optional overrides)
└── src/
    ├── trip_agent.py                   # agent: tools, prompt, geocoding, HITL middleware
    ├── llm.py                          # Nebius model factory (get_model)
    ├── catalog.py                      # CATALOG_ID shared with the frontend
    └── a2ui/schemas/stop_card.json     # reference StopCard tree (for tweaking)

src/                                    # Next.js app
├── app/
│   ├── layout.tsx                      # root layout + Providers
│   ├── page.tsx                        # "/" → redirects to /trip
│   ├── trip/page.tsx                   # the app: chat (left) + workspace (right)
│   ├── globals.css
│   └── api/copilotkit/route.ts         # bridge: CopilotRuntime + HttpAgent → :8123/trip
├── components/
│   ├── Providers.tsx                   # <CopilotKit> + trip mirror renderer
│   ├── TripWorkspace.tsx               # map + current surface + onAction (the loop glue)
│   ├── TripMap.tsx / TripMapInner.tsx  # Leaflet map (pins + route + hover tooltips)
│   ├── ItineraryPanel.tsx              # "Your plan" overlay — itinerary grouped by day
│   └── Split.tsx                       # draggable two-pane layout
└── a2ui/
    ├── catalog/
    │   ├── definitions.ts              # Zod prop schemas + agent-facing descriptions
    │   ├── renderers.tsx               # the React renderers (Card, Button, charts, …)
    │   └── index.ts                    # createCatalog() → catalog + catalogSchema
    ├── MirrorRenderer.tsx              # forwards A2UI ops from chat → surface bus
    ├── surface-bus.ts                  # tiny per-agent event bus (chat → canvas)
    ├── theme.css                       # brand tokens, scoped to .a2ui-surface
    └── trip-store.ts                   # approved stops; bridges approve events → map
```

### The key files, in one line each

- **`trip_agent.py`** — `propose_stop` builds a StopCard from catalog components with the
  stop (geocoded to its real location) inlined into the Approve button's context;
  `finish_trip` builds the completion card. The `OneProposalPerTurn` middleware ends the
  turn after one proposal (the human-in-the-loop guarantee); the system prompt sets the
  conversation-vs-planning behaviour and forbids re-proposing an added place.
- **`route.ts`** — registers the `trip_agent` `HttpAgent` (aliased to `default`); sets
  `a2ui: { injectA2UITool: false }` because the Python agent emits the ops itself.
- **`TripWorkspace.tsx`** — the glue. Renders the map over the current surface, and its
  `onAction` pins approved stops, clears the consumed card, and re-runs the agent.
- **`trip-store.ts`** — a minimal external store of approved stops the map subscribes to.
- **`catalog/`** — the design system the agent draws from; `CATALOG_ID` is shared with
  `agent/src/catalog.py` so `createSurface` resolves to these renderers.

---

## The A2UI catalog

A2UI never ships layout code or arbitrary markup to the browser — the agent only
references **component types from a catalog you define**. Each component is a Zod prop
schema (`definitions.ts`) paired with a React renderer (`renderers.tsx`), registered
via `createCatalog()` (`index.ts`). This is why an open model can drive the UI safely:
it composes from primitives you already trust, and the look stays entirely yours.

The shared catalog includes layout (`Stack`, `Row`, `Grid`, `Section`, `Card`,
`Divider`), content (`Heading`, `Text`, `Overline`, `Badge`, `Callout`, `BulletList`),
data viz (`StatCard`, `BarChart`, `HorizontalBarChart`, `LineChart`, `DonutChart`,
`ScatterChart`, `DataTable`), and interactive (`Button`, `ChoiceChips`). The StopCard
is composed from `Card` + `Stack` + `Overline` + `Heading` + `Text` + `Badge` + `Row`
+ `Button` — **no custom renderers were needed**.

---

## Customizing

- **Change the card design** — edit `build_stop_card()` in `trip_agent.py` (reorder /
  add catalog components). `agent/src/a2ui/schemas/stop_card.json` is a reference
  example of the resulting tree.
- **Tune Atlas's behaviour** — edit `SYSTEM_PROMPT` in `trip_agent.py` (pacing, how
  many stops before finishing, tone).
- **Swap the model** — set `NEBIUS_MODEL` in `agent/.env`. No code change.
- **Restyle** — `src/a2ui/theme.css` (catalog surfaces) and `src/app/globals.css`
  (app shell). The map's look is the CARTO dark tiles + pin styles in `TripMapInner.tsx`.
- **Coordinate accuracy** — `geocode()` in `trip_agent.py` resolves pins via
  OpenStreetMap/Nominatim, bounded to the stop's region. Swap in a keyed geocoder
  (Google / Mapbox) there for venue-precise pins.
- **Conversation vs planning** — the two-mode behaviour (chat freely, propose only when
  ready) lives in `SYSTEM_PROMPT`; the one-proposal pause lives in the
  `OneProposalPerTurn` middleware — both in `trip_agent.py`.
- **Add a new component the agent can use** — add a Zod definition + a renderer to the
  catalog, then reference it from a tool's component tree.

---

## Acknowledgements

This project is adapted from CopilotKit's official **A2UI PDF Analyst** showcase:

> <https://github.com/CopilotKit/CopilotKit/tree/main/examples/showcases/a2ui-pdf-analyst>

The shared A2UI infrastructure — the catalog + renderer system, `surface-bus.ts`,
`MirrorRenderer.tsx`, the `HttpAgent` → Python bridge, the `Split` layout, and the
catalog component renderers — derives from that example. Atlas adapts it to a
trip-planning domain, replaces the PDF agents with a single trip agent, swaps the
runtime model to an open model on **Nebius Token Factory**, and adds the Leaflet map
and per-stop approval loop.

Built with [CopilotKit](https://copilotkit.ai), the [A2UI protocol](https://a2ui.org),
[AG-UI](https://github.com/ag-ui-protocol), and [Nebius Token Factory](https://tokenfactory.nebius.com/).

### License

This repository's source code is available under the [MIT License](LICENSE).

_Map data: tiles © [CARTO](https://carto.com/attribution), map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors. (Hidden on the map via `attributionControl={false}`; set it to `true` to show the credit on screen instead.)_
