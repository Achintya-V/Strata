"""Strata + LiteLLM — memory extraction with ANY LLM provider.

LiteLLM gives Strata a unified interface to 100+ models. Set the provider
in config.yaml or via environment variables.

Install:
    pip install strata-memory[litellm]

Usage examples:

# OpenAI
OPENAI_API_KEY=sk-... python examples/litellm_chatbot.py

# Groq (fast, free tier)
GROQ_API_KEY=gsk_... STRATA_LLM_COMPILE_MODEL=groq/llama-3.1-8b-instant python ...

# Gemini
GEMINI_API_KEY=... STRATA_LLM_COMPILE_MODEL=gemini/gemini-1.5-flash python ...

# Ollama (local, no API key)
ollama pull llama3.1
STRATA_LLM_COMPILE_MODEL=ollama/llama3.1 STRATA_LLM_LITELLM_API_BASE=http://localhost:11434 python ...

# NVIDIA NIM
NVIDIA_API_KEY=nvapi-... STRATA_LLM_COMPILE_MODEL=nvidia_nim/meta/llama-3.1-8b-instruct python ...

# Azure OpenAI
AZURE_API_KEY=... AZURE_API_BASE=https://... STRATA_LLM_COMPILE_MODEL=azure/gpt-4o python ...
"""
from __future__ import annotations

import os
from strata import Memory
from strata.config import Config, LLMConfig, PipelineConfig


def build_memory(model: str, api_base: str | None = None) -> Memory:
    """Build a Memory instance configured for a specific LiteLLM model."""
    llm_cfg = LLMConfig(
        provider="litellm",
        compile_model=model,
        litellm_api_base=api_base,
    )
    config = Config(llm=llm_cfg)
    return Memory(repo_path="./chat-memory-litellm", config=config)


def demo(model: str, api_base: str | None = None) -> None:
    print(f"\n{'='*60}")
    print(f"Testing with model: {model}")
    print(f"{'='*60}")

    m = build_memory(model, api_base)

    # Ingest some facts
    m.add("I'm Alice. I prefer dark roast coffee and work at NVIDIA.", user_id="alice")
    m.add("I just switched jobs — now I work at Google on the Gemini team.", user_id="alice")
    m.flush()

    # Search — should show superseded job
    context = m.search("alice employer job", user_id="alice", format="context")
    print("\nPacked context:")
    print(context or "(empty)")

    # Check profile claims
    profile = m.get("u/alice/user/profile")
    if profile:
        print(f"\nClaims ({len(profile['claims'])} total):")
        for c in profile["claims"]:
            status = "ACTIVE" if not c.get("valid_until") else f"superseded {c['valid_until']}"
            print(f"  [{status}] {c['text']}")

    m.close()
    print(f"\nExtractor used: {m.stats()['extractor'] if hasattr(m, '_closed') else 'closed'}")


if __name__ == "__main__":
    # Auto-detect model from environment
    model = os.environ.get("STRATA_LLM_COMPILE_MODEL",
            os.environ.get("LITELLM_MODEL", "gpt-4o-mini"))
    api_base = os.environ.get("STRATA_LLM_LITELLM_API_BASE")

    demo(model, api_base)

    print("\n\n--- Provider quick-reference ---")
    providers = [
        ("OpenAI",    "gpt-4o-mini",                       "OPENAI_API_KEY"),
        ("Anthropic", "claude-haiku-4-5-20251001",          "ANTHROPIC_API_KEY"),
        ("Groq",      "groq/llama-3.1-8b-instant",          "GROQ_API_KEY"),
        ("Gemini",    "gemini/gemini-1.5-flash",             "GEMINI_API_KEY"),
        ("Ollama",    "ollama/llama3.1",                     "none (local)"),
        ("NVIDIA",    "nvidia_nim/meta/llama-3.1-8b-instruct","NVIDIA_API_KEY"),
        ("Together",  "together_ai/meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo", "TOGETHERAI_API_KEY"),
        ("Bedrock",   "bedrock/anthropic.claude-3-haiku-20240307-v1:0", "AWS credentials"),
        ("Cohere",    "command-r-plus",                      "COHERE_API_KEY"),
        ("Azure",     "azure/gpt-4o",                        "AZURE_API_KEY + AZURE_API_BASE"),
    ]
    print(f"{'Provider':<12} {'Model':<55} {'API Key'}")
    print("-" * 90)
    for name, mod, key in providers:
        print(f"{name:<12} {mod:<55} {key}")
