"""LiteLLM extractor — use ANY LLM for memory extraction (§5.7).

LiteLLM provides a unified interface to 100+ LLMs with one consistent API:
    OpenAI:     gpt-4o-mini, gpt-4o
    Anthropic:  claude-haiku-4-5-20251001, claude-sonnet-5
    Google:     gemini/gemini-1.5-flash, gemini/gemini-1.5-pro
    Ollama:     ollama/llama3.1, ollama/mistral  (local, no API key)
    NVIDIA:     nvidia_nim/meta/llama-3.1-8b-instruct
    Groq:       groq/llama-3.1-8b-instant  (very fast)
    Together:   together_ai/mistralai/Mistral-7B-Instruct-v0.2
    Azure:      azure/gpt-4o
    Bedrock:    bedrock/anthropic.claude-3-haiku-20240307-v1:0
    Cohere:     command-r-plus
    ... and 90+ more: https://docs.litellm.ai/docs/providers

Install:
    pip install strata-memory[litellm]

Configure via env or config.yaml:
    # config.yaml
    llm:
      provider: litellm
      compile_model: gpt-4o-mini          # any litellm model string
      litellm_api_base: http://localhost:11434  # for Ollama

    # or via environment
    STRATA_LLM_PROVIDER=litellm
    STRATA_LLM_COMPILE_MODEL=groq/llama-3.1-8b-instant
    OPENAI_API_KEY=sk-...        # or GROQ_API_KEY, ANTHROPIC_API_KEY, etc.

Structured output strategy:
    LiteLLM uses JSON mode (not tool-use) for maximum model compatibility.
    Models that support tool-use (OpenAI, Claude) use it automatically via
    LiteLLM's tool_choice parameter. Others fall back to JSON mode with
    a schema-guided prompt.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from pydantic import ValidationError

from ...config import Config
from ...models import PageOp, PageOpBatch, RawEntry
from ...obs import Ledgers, log
from ...schema import Schema
from .base import ExtractionError
from .anthropic_llm import SYSTEM_PROMPT

# Models that support native tool-use via LiteLLM
_TOOL_USE_MODELS = {
    "gpt-4", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo",
    "claude-", "anthropic/",                          # prefix match
    "gemini/gemini-1.5", "gemini/gemini-2",
    "groq/",                                          # groq supports tool_choice
    "together_ai/mistralai/Mixtral",
}

_JSON_SCHEMA_PROMPT = """
Return a JSON object matching this exact schema. No explanation, no markdown, only the JSON object:

{schema}

The JSON must have an "ops" array. Each op must have:
- "op": "create" or "update"
- "type": page type from the available types
- "title": string
- "summary": string
- "body": string
- "confidence": float 0-1
- "claims": array of claim objects, each with "text", "subject", "provenance", "confidence"
"""


class LiteLLMExtractor:
    """Universal LLM extractor using LiteLLM.

    Supports tool-use for capable models (OpenAI, Claude, Gemini, Groq)
    and falls back to JSON mode for all others (Ollama, Together, etc.).

    Examples:
        # OpenAI (set OPENAI_API_KEY)
        config.llm.compile_model = "gpt-4o-mini"

        # Groq (fast, set GROQ_API_KEY)
        config.llm.compile_model = "groq/llama-3.1-8b-instant"

        # Ollama (local, no API key)
        config.llm.compile_model = "ollama/llama3.1"
        config.llm.litellm_api_base = "http://localhost:11434"

        # Google Gemini (set GEMINI_API_KEY)
        config.llm.compile_model = "gemini/gemini-1.5-flash"

        # NVIDIA NIM (set NVIDIA_API_KEY)
        config.llm.compile_model = "nvidia_nim/meta/llama-3.1-8b-instruct"
    """

    name = "litellm"

    def __init__(self, config: Config, ledgers: Optional[Ledgers] = None):
        try:
            import litellm
            self._litellm = litellm
        except ImportError as exc:
            raise ImportError(
                "LiteLLM extractor needs the [litellm] extra: "
                "pip install strata-memory[litellm]"
            ) from exc

        self.model = config.llm.compile_model
        self.ledgers = ledgers
        self.api_base = getattr(config.llm, "litellm_api_base", None)
        self._use_tools = self._supports_tool_use(self.model)

        # Silence litellm's verbose logging unless debug mode
        import os
        if not os.environ.get("LITELLM_LOG"):
            self._litellm.suppress_debug_info = True
            self._litellm.verbose = False

    @staticmethod
    def _supports_tool_use(model: str) -> bool:
        """Check if the model supports tool/function calling."""
        model_lower = model.lower()
        for pattern in _TOOL_USE_MODELS:
            if model_lower.startswith(pattern.lower()) or pattern.lower() in model_lower:
                return True
        return False

    def _call_with_tools(self, messages: list[dict]) -> dict:
        """Use tool_choice for models that support it (OpenAI, Claude, etc.)"""
        tool_schema = PageOpBatch.model_json_schema()
        tool_schema["additionalProperties"] = False

        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
            max_tokens=4096,
            tools=[{
                "type": "function",
                "function": {
                    "name": "emit_page_ops",
                    "description": "Emit the page operations extracted from the raw entry.",
                    "parameters": tool_schema,
                },
            }],
            tool_choice={"type": "function", "function": {"name": "emit_page_ops"}},
        )
        if self.api_base:
            kwargs["api_base"] = self.api_base

        response = self._litellm.completion(**kwargs)
        self._record_tokens(response)

        # Extract tool call arguments
        message = response.choices[0].message
        if message.tool_calls:
            return json.loads(message.tool_calls[0].function.arguments)
        raise ExtractionError("model returned no tool_call")

    def _call_with_json(self, prompt: str) -> dict:
        """Use JSON mode for models without tool-use (Ollama, etc.)"""
        schema_str = json.dumps(PageOpBatch.model_json_schema(), indent=2)
        system = SYSTEM_PROMPT + "\n" + _JSON_SCHEMA_PROMPT.format(schema=schema_str)

        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4096,
        )
        if self.api_base:
            kwargs["api_base"] = self.api_base

        # Enable JSON mode if supported
        try:
            kwargs["response_format"] = {"type": "json_object"}
            response = self._litellm.completion(**kwargs)
        except Exception:
            # Model doesn't support response_format — remove it and retry
            kwargs.pop("response_format", None)
            response = self._litellm.completion(**kwargs)

        self._record_tokens(response)
        content = response.choices[0].message.content or "{}"

        # Strip markdown code fences if model wrapped the JSON
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(
                l for l in lines
                if not l.strip().startswith("```")
            ).strip()

        return json.loads(content)

    def _record_tokens(self, response: Any) -> None:
        if self.ledgers and getattr(response, "usage", None):
            self.ledgers.record_tokens(
                self.model,
                response.usage.prompt_tokens or 0,
                response.usage.completion_tokens or 0,
                "extract",
            )

    def _build_prompt(self, raw: RawEntry, index_summary: str, schema: Schema) -> str:
        type_lines = "\n".join(
            f"- {name} (decay: {rule.decay})" for name, rule in schema.page_types.items()
        ) or "- session"
        return (
            f"Page types available:\n{type_lines}\n\n"
            f"Existing pages (id | title | tags):\n{index_summary or '(none yet)'}\n\n"
            f"Raw entry (source_type={raw.source_type}, user_id={raw.user_id or 'none'}, "
            f"recorded {raw.created}):\n<raw>\n{raw.text}\n</raw>"
        )

    def extract(self, raw: RawEntry, index_summary: str, schema: Schema) -> list[PageOp]:
        prompt = self._build_prompt(raw, index_summary, schema)
        messages: list[dict] = [{"role": "user", "content": prompt}]
        last_error = ""

        for attempt in (1, 2):
            try:
                if self._use_tools:
                    data = self._call_with_tools(messages)
                else:
                    data = self._call_with_json(prompt)

                return PageOpBatch.model_validate(data).ops

            except (ValidationError, json.JSONDecodeError) as e:
                last_error = str(e)
                log.warning("litellm extraction validation failed (attempt %d): %s",
                            attempt, last_error)
                if attempt == 1 and self._use_tools:
                    # For tool-use models: add retry context
                    messages = messages + [
                        {"role": "assistant", "content": [
                            {"type": "tool_use", "id": "retry_1",
                             "name": "emit_page_ops", "input": data if 'data' in dir() else {}},
                        ]},
                        {"role": "user", "content": [
                            {"type": "tool_result", "tool_use_id": "retry_1", "is_error": True,
                             "content": f"Validation failed, fix and re-emit:\n{last_error}"},
                        ]},
                    ]
            except Exception as e:
                last_error = str(e)
                log.error("litellm extraction error (attempt %d, model=%s): %s",
                          attempt, self.model, last_error)
                if attempt == 2:
                    break

        raise ExtractionError(
            f"litellm extraction failed after retry (model={self.model}): {last_error}"
        )
