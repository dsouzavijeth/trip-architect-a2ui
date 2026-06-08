"""Model factory — points the agents at Nebius Token Factory instead of OpenAI.

Nebius Token Factory is OpenAI-compatible, so we reuse langchain-openai's
ChatOpenAI and just override base_url + api_key. Both the main agent and the
secondary "render" LLM call get_model(), so the whole stack runs on one open
model with a single switch here.
"""
from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

NEBIUS_BASE_URL = os.environ.get(
    "NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1"
)

# A2UI works by the agent calling tools (and, in dynamic mode, a forced
# tool_choice on the secondary LLM), so pick a model with strong, reliable
# tool-calling. Good Nebius options: Qwen/Qwen2.5-72B-Instruct,
# meta-llama/Llama-3.3-70B-Instruct, deepseek-ai/DeepSeek-V3.
# Confirm the exact ID in the Token Factory playground.
NEBIUS_MODEL = os.environ.get("NEBIUS_MODEL", "Qwen/Qwen2.5-72B-Instruct")


def get_model(temperature: float = 0.0) -> ChatOpenAI:
    """Return a ChatOpenAI bound to Nebius Token Factory.

    Pass the result straight to langchain's create_agent(model=...) and use it
    for the secondary render LLM too.
    """
    return ChatOpenAI(
        model=NEBIUS_MODEL,
        base_url=NEBIUS_BASE_URL,
        api_key=os.environ["NEBIUS_API_KEY"],
        temperature=temperature,
    )
