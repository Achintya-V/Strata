"""Shared plumbing for the memory benchmarks: metrics, result records, and the
optional Nemotron answerer.

Two evaluation modes, honestly separated:

- **retrieval-only** (default, fully offline): does the gold answer appear in
  what Strata returns? Two levels — inside the token-budgeted packed context
  (what an integrator would actually paste into a prompt), and inside the full
  text of the top-k retrieved pages (retrieval-stack recall).
- **--with-llm**: Nemotron answers the question from the packed context; graded
  with SQuAD-style normalized exact-match and token-F1 against gold.

Substring answer-presence is a recall proxy, not an official benchmark score —
never quote these numbers as LoCoMo/LongMemEval leaderboard results.
"""
from __future__ import annotations

import re
import string
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from strata.util import est_tokens

# ---------------- text metrics (SQuAD-style) ----------------

_ARTICLES = re.compile(r"\b(a|an|the)\b")


def normalize(text: str) -> str:
    text = str(text).lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = _ARTICLES.sub(" ", text)
    return " ".join(text.split())


def presence(haystack: str, gold: str) -> bool:
    """Normalized-substring answer presence (recall proxy; brittle for
    paraphrased golds — documented)."""
    g = normalize(gold)
    return bool(g) and g in normalize(haystack)


def exact_match(pred: str, gold: str) -> bool:
    return normalize(pred) == normalize(gold)


def token_f1(pred: str, gold: str) -> float:
    pred_tokens, gold_tokens = normalize(pred).split(), normalize(gold).split()
    if not pred_tokens or not gold_tokens:
        return float(pred_tokens == gold_tokens)
    common: dict[str, int] = {}
    for t in pred_tokens:
        common[t] = common.get(t, 0) + 1
    overlap = sum(min(common.get(t, 0), gold_tokens.count(t)) for t in set(gold_tokens))
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred_tokens)
    recall = overlap / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * p))]


# ---------------- result records ----------------

@dataclass
class CaseResult:
    qid: str
    category: str
    in_context: bool          # gold present in packed context
    in_pages: bool            # gold present in top-k pages' full text
    latency_ms: float
    context_tokens: int
    em: Optional[bool] = None      # LLM mode only
    f1: Optional[float] = None
    prediction: str = ""


@dataclass
class BenchmarkResult:
    name: str
    mode: str
    cases: list[CaseResult] = field(default_factory=list)
    skipped: int = 0               # unanswerable/adversarial items excluded from aggregates
    notes: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)   # benchmark-native metrics

    @property
    def n(self) -> int:
        return len(self.cases)

    def rate(self, attr: str) -> float:
        vals = [getattr(c, attr) for c in self.cases if getattr(c, attr) is not None]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    def mean(self, attr: str) -> float:
        vals = [getattr(c, attr) for c in self.cases if getattr(c, attr) is not None]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    def p50(self, attr: str) -> float:
        return percentile([getattr(c, attr) for c in self.cases], 0.5)

    def by_category(self) -> dict[str, dict[str, Any]]:
        cats: dict[str, list[CaseResult]] = {}
        for c in self.cases:
            cats.setdefault(c.category, []).append(c)
        out = {}
        for cat, items in sorted(cats.items()):
            out[cat] = {
                "n": len(items),
                "in_context": round(sum(c.in_context for c in items) / len(items), 4),
                "in_pages": round(sum(c.in_pages for c in items) / len(items), 4),
            }
            f1s = [c.f1 for c in items if c.f1 is not None]
            if f1s:
                out[cat]["f1"] = round(sum(f1s) / len(f1s), 4)
        return out

    def summary(self) -> dict[str, Any]:
        s: dict[str, Any] = {
            "benchmark": self.name, "mode": self.mode, "cases": self.n,
            "skipped": self.skipped,
            "answer_in_context": self.rate("in_context"),
            "answer_in_pages": self.rate("in_pages"),
            "context_tokens_p50": self.p50("context_tokens"),
            "latency_ms_p50": round(self.p50("latency_ms"), 1),
            "notes": self.notes,
        }
        if any(c.f1 is not None for c in self.cases):
            s["em"] = self.rate("em")
            s["f1"] = self.mean("f1")
        s.update(self.metrics)
        return s


# ---------------- QA evaluation against one Memory ----------------

def evaluate_question(memory, question: str, gold: str, user_id: str, qid: str,
                      category: str, k: int, llm=None) -> CaseResult:
    """Retrieve for one question, measure presence (and optionally answer+grade)."""
    t0 = time.perf_counter()
    context = memory.search(question, user_id=user_id, top_k=k, format="context")
    hits = memory.searcher.search(question, user_id=user_id, top_k=k)
    latency_ms = (time.perf_counter() - t0) * 1000

    page_text = []
    for h in hits:
        parsed = memory.repo.read_page(h.page_id)
        if parsed:
            page, body = parsed
            page_text.append("\n".join([page.title, page.summary, body,
                                        *(c.text for c in page.claims)]))
    result = CaseResult(
        qid=qid, category=category,
        in_context=presence(context, gold),
        in_pages=presence("\n".join(page_text), gold),
        latency_ms=latency_ms, context_tokens=est_tokens(context) if context else 0,
    )
    if llm is not None:
        prediction = answer_with_llm(llm, context, question)
        result.prediction = prediction
        result.em = exact_match(prediction, gold)
        result.f1 = token_f1(prediction, gold)
    return result


# "/no_think" disables Nemotron's reasoning mode — otherwise the token budget
# is consumed by a <think> block before any answer is emitted (harmless plain
# text for models without the directive).
ANSWER_SYSTEM = (
    "Answer the question using ONLY the memory context provided. "
    "Reply with the shortest possible answer span — no explanation, no sentence. "
    "If the context does not contain the answer, reply exactly: unknown /no_think"
)


def answer_with_llm(llm, context: str, question: str) -> str:
    try:
        return llm.chat(
            ANSWER_SYSTEM,
            [{"role": "user", "content": f"{context}\n\nQuestion: {question}"}],
            temperature=0.0, max_tokens=256,
        ).strip()
    except Exception as e:
        return f"__llm_error__ {e}"


def fresh_memory(root, name: str, force_heuristic: bool = True):
    """A Memory on a fresh repo under `root`, tuned for benchmark ingest: no
    background worker, and the deterministic heuristic extractor by default so
    runs are reproducible (pass force_heuristic=False + ANTHROPIC_API_KEY to
    measure LLM-compiled memory instead)."""
    from strata import Memory
    return Memory(repo_path=root / name, start_worker=False,
                  force_heuristic=force_heuristic)
