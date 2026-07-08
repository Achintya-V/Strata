import os

import pytest

from strata import Memory


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    """Tests always run offline against the heuristic extractor."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture()
def mem(tmp_path):
    m = Memory(repo_path=tmp_path / "mem", start_worker=False)
    yield m
    m.close()


@pytest.fixture()
def mem_factory(tmp_path):
    """Create Memory instances on demand (same or different repos)."""
    created = []

    def factory(name="mem", **kwargs):
        m = Memory(repo_path=tmp_path / name, start_worker=kwargs.pop("start_worker", False),
                   **kwargs)
        created.append(m)
        return m

    yield factory
    for m in created:
        m.close()


def add_and_flush(m: Memory, text: str, **kwargs) -> dict:
    result = m.add(text, **kwargs)
    m.flush()
    return result
