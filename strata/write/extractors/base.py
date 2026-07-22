"""Extractor protocol + selection.

An Extractor turns one raw entry into a list of PageOps. It sees a compact
index summary (existing page ids/titles/tags) so it routes updates to existing
pages instead of creating duplicates, and the target user's existing active
claims so it can mark supersessions deliberately.
"""
from __future__ import annotations

import os
from typing import Optional, Protocol

from ...config import Config
from ...models import PageOp, RawEntry
from ...obs import Ledgers, log
from ...schema import Schema


class ExtractionError(RuntimeError):
    pass


class Extractor(Protocol):
    name: str

    def extract(self, raw: RawEntry, index_summary: str, schema: Schema) -> list[PageOp]: ...


def get_extractor(config: Config, ledgers: Optional[Ledgers] = None,
                  force_heuristic: bool = False) -> Extractor:
    """Select the best available extractor.

    Priority:
      1. force_heuristic=True → HeuristicExtractor (always offline)
      2. provider=litellm     → LiteLLMExtractor (any model via litellm)
      3. provider=anthropic   → AnthropicExtractor (native tool-use)
      4. fallback             → HeuristicExtractor
    """
    from .heuristic import HeuristicExtractor

    if force_heuristic:
        return HeuristicExtractor()

    provider = config.llm.provider.lower()

    # LiteLLM — universal provider (OpenAI, Ollama, Groq, Gemini, NVIDIA, etc.)
    if provider == "litellm":
        try:
            from .litellm_extractor import LiteLLMExtractor
            return LiteLLMExtractor(config, ledgers)
        except ImportError:
            log.warning("provider=litellm but `litellm` not installed "
                        "(pip install strata-memory[litellm]) — falling back to heuristic")

    # Native Anthropic (tool-use, best structured output quality)
    elif provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from .anthropic_llm import AnthropicExtractor
            return AnthropicExtractor(config, ledgers)
        except ImportError:
            log.warning("ANTHROPIC_API_KEY set but `anthropic` package missing "
                        "(pip install strata-memory[llm]) — using heuristic extractor")

    # Auto-detect litellm if API keys are set for non-anthropic providers
    elif provider not in ("anthropic", "heuristic"):
        # openai, groq, gemini, ollama, nvidia_nim, together_ai, azure, bedrock, cohere...
        try:
            from .litellm_extractor import LiteLLMExtractor
            return LiteLLMExtractor(config, ledgers)
        except ImportError:
            log.warning("provider=%s detected but `litellm` not installed "
                        "(pip install strata-memory[litellm]) — using heuristic", provider)

    return HeuristicExtractor()
