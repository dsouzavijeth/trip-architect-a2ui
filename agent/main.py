"""FastAPI server exposing the Trip Architect AG-UI agent.

Run with:  uvicorn main:app --port 8123 --reload
"""
from __future__ import annotations

import os

import uvicorn
from ag_ui_langgraph import add_langgraph_fastapi_endpoint
from copilotkit import LangGraphAGUIAgent
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from src.trip_agent import graph as trip_graph  # noqa: E402

app = FastAPI(title="Atlas Trip Architect Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# LangGraph's default recursion_limit is 25; ag_ui_langgraph builds its own
# RunnableConfig per run, so pass it here. 50 is plenty for the trip loop.
_AGENT_CONFIG = {"recursion_limit": 50}

add_langgraph_fastapi_endpoint(
    app=app,
    agent=LangGraphAGUIAgent(
        name="trip_agent",
        description="Trip architect: proposes stops one at a time as A2UI cards.",
        graph=trip_graph,
        config=_AGENT_CONFIG,
    ),
    path="/trip",
)


@app.get("/")
def root():
    return {"ok": True, "agents": {"trip_agent": "/trip/"}}


def main():
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8123")),
        reload=True,
    )


if __name__ == "__main__":
    main()
