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
    """LLM extraction when a key + SDK are available, heuristic floor otherwise."""
    from .heuristic import HeuristicExtractor

    if not force_heuristic:
        if config.llm.provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                from .anthropic_llm import AnthropicExtractor
                return AnthropicExtractor(config, ledgers)
            except ImportError:
                log.warning("ANTHROPIC_API_KEY set but `anthropic` package missing "
                            "(pip install strata-memory[llm]) — using heuristic extractor")
        elif config.llm.provider == "azure_openai" and os.environ.get("AZURE_OPENAI_API_KEY"):
            try:
                from .azure_openai_llm import AzureOpenAIExtractor
                return AzureOpenAIExtractor(config, ledgers)
            except ImportError:
                log.warning("AZURE_OPENAI_API_KEY set but `openai` package missing "
                            "— using heuristic extractor")
    return HeuristicExtractor()
