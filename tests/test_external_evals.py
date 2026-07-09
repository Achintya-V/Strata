"""Tests for the add-on modules (benchmarks/memory_evals + chatbot) — nothing
here touches or depends on internals beyond strata's public surface."""
from pathlib import Path

import pytest

from benchmarks.memory_evals.common import (BenchmarkResult, CaseResult,
                                            exact_match, normalize, presence,
                                            token_f1)
from benchmarks.memory_evals.inhouse import SCENARIO, run_inhouse
from benchmarks.memory_evals.locomo import load_locomo, run_locomo
from benchmarks.memory_evals.longmemeval import load_longmemeval, run_longmemeval

FIXTURES = Path(__file__).parent.parent / "benchmarks" / "memory_evals" / "fixtures"


# ---------------- metrics ----------------

def test_normalize_strips_articles_punct_case():
    assert normalize("The  Lisbon, Marathon!") == "lisbon marathon"
    assert normalize("") == ""


def test_presence():
    assert presence("He finished the Lisbon marathon in June", "Lisbon Marathon")
    assert not presence("something else entirely", "Lisbon Marathon")
    assert not presence("anything", "")             # empty gold never matches


def test_exact_match_and_f1():
    assert exact_match("The cello!", "cello")
    assert token_f1("plays the cello", "cello") == pytest.approx(2 * (1/2) * 1 / (1/2 + 1))
    assert token_f1("", "cello") == 0.0
    assert token_f1("cello", "cello") == 1.0


def test_benchmark_result_aggregation():
    r = BenchmarkResult(name="x", mode="test")
    r.cases = [CaseResult("a", "c1", True, True, 10.0, 100),
               CaseResult("b", "c1", False, True, 30.0, 200)]
    assert r.rate("in_context") == 0.5
    assert r.rate("in_pages") == 1.0
    assert r.by_category()["c1"]["n"] == 2
    assert r.summary()["cases"] == 2


# ---------------- adapters on format fixtures ----------------

def test_locomo_fixture_end_to_end(tmp_path):
    result = run_locomo(FIXTURES / "locomo_sample.json", tmp_path, k=5)
    assert result.n == 3                            # category-5 adversarial skipped
    assert result.skipped == 1
    # answers appear verbatim in session text -> retrieval-level recall must be perfect
    assert result.rate("in_pages") == 1.0
    cats = result.by_category()
    assert any(c.startswith("4:") for c in cats)    # category labels preserved
    assert all(c.latency_ms >= 0 for c in result.cases)


def test_locomo_loader_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_locomo(bad)


def test_longmemeval_fixture_end_to_end(tmp_path):
    result = run_longmemeval(FIXTURES / "longmemeval_sample.json", tmp_path, k=5)
    assert result.n == 2                            # _abs abstention instance skipped
    assert result.skipped == 1
    assert result.rate("in_pages") == 1.0
    # knowledge-update case: current city (Porto) must be in the packed context
    ku = next(c for c in result.cases if c.category == "knowledge-update")
    assert ku.in_context


def test_longmemeval_loader_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('"just a string"', encoding="utf-8")
    with pytest.raises(ValueError):
        load_longmemeval(bad)


# ---------------- in-house ----------------

def test_inhouse_scenario_deterministic(tmp_path):
    result = run_inhouse(tmp_path, k=5)
    expected_chains = 5                             # every SCENARIO pair contradicts once
    assert result.metrics["hit_at_k"] == 1.0
    assert result.metrics["current_fact_rate"] == 1.0
    assert result.metrics["stale_leak_rate"] == 0.0
    assert result.n == expected_chains
    assert sum(len(s) for _, s in SCENARIO) - expected_chains == result.n  # pairs -> chains


def test_inhouse_against_existing_repo(tmp_path):
    from strata import Memory
    m = Memory(repo_path=tmp_path / "user-repo", start_worker=False)
    m.add("I prefer window seats", user_id="u")
    m.add("I prefer aisle seats now.", user_id="u")
    m.flush()
    m.close()
    result = run_inhouse(tmp_path, k=5, repo=tmp_path / "user-repo")
    assert result.n == 1
    assert result.metrics["current_fact_rate"] == 1.0


# ---------------- chatbot client ----------------

def test_nemotron_client_env_handling(monkeypatch):
    from chatbot.llm import DEFAULT_BASE_URL, DEFAULT_MODEL, NemotronClient
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    c = NemotronClient(api_key="")                  # explicit empty: unavailable
    # .env at project root may set a real key; explicit args must win
    assert c.model and c.base_url
    c2 = NemotronClient(api_key="test", model="m", base_url="http://x")
    assert c2.available and c2.model == "m" and c2.base_url == "http://x"
    c3 = NemotronClient(api_key=" ")
    assert not c3.available
    with pytest.raises(RuntimeError):
        c3.chat("sys", [])
