# Strata

**Git-native memory layer for any chatbot.** Mem0's integration shape —
`pip install strata-memory`, `Memory().add()`, `Memory().search()` — with a
fundamentally different storage bet: your memory lives in a folder of plain
markdown files in a git repo, not locked in a vector database.
`cat` it, `grep` it, `git diff` it, keep it forever. **The files ARE the memory.**

```python
from strata import Memory

m = Memory(repo_path="./chat-memory")
m.add("I'm vegetarian and prefer window seats", user_id="alice")
m.search("alice seating", user_id="alice", format="context")
```

## Install

```bash
# Core — zero external deps, offline heuristic extractor, BM25 search
pip install strata-memory

# Recommended — adds semantic vector search (L2)
pip install strata-memory[vector]

# Full stack — vector + LLM extraction + PII + MCP + REST API + crypto-shred
pip install strata-memory[all]
```

Optional extras:

| Extra | Adds | Use when |
|-------|------|----------|
| `[vector]` | sqlite-vec + model2vec | Better retrieval, semantic search |
| `[llm]` | anthropic | LLM extraction (set `ANTHROPIC_API_KEY`) |
| `[pii]` | presidio-analyzer | Production PII detection (30+ types) |
| `[mcp]` | mcp | Claude Code/Desktop MCP server |
| `[api]` | fastapi + uvicorn | REST API server |
| `[crypto]` | cryptography | AES-256-GCM crypto-shred erasure |
| `[all]` | everything above | Full production stack |

Everything degrades gracefully: no API key → offline heuristic extractor;
no vector extra → lexical BM25 only. Core never imports torch.

## What makes it different

- **Bi-temporal claim ledger.** Every fact is a claim with `valid_from` /
  `valid_until` / `recorded_at`, a provenance type, a confidence score, and a
  source citation. Contradictions supersede — they never silently overwrite and
  never silently persist. `search(..., as_of="2026-05-01")` answers "what did
  we believe then"; `git checkout` time-travels the records themselves.
- **Provenance & trust.** `user_stated | agent_inferred | tool_derived |
  imported | human_edited`, with per-provenance confidence ceilings from
  `schema.md` (imported facts cap at 0.6). Search ranks user-stated facts above
  inferences at equal relevance.
- **Async write path.** `add()` appends the raw source, enqueues, and returns in
  milliseconds. A background worker batches, compiles (LLM or offline
  heuristic), resolves contradictions, and makes one git commit per cycle.
  Read-your-writes is **eventual** for compiled pages (raw text is searchable
  immediately; call `flush()` to force compilation).
- **Memory PRs.** Injection-shaped or low-confidence writes are quarantined to
  a review queue instead of stored silently (`review: auto`, the default;
  `gated` reviews everything, `off` disables). `strata review` accepts/rejects;
  every decision is a commit.
- **Compliance-grade erasure + audit.** All of a user's data lives under two
  path prefixes. `strata forget <user>` scrubs the working tree and writes a
  tombstone; `--rewrite` additionally purges all git history via
  git-filter-repo (provable erasure). `git log` is the audit trail; the ops
  ledger records erasures, retention deletions, and review decisions.
- **PII gate.** Regex scanner in core (Presidio via `[pii]` extra):
  `tag | mask | block` policies applied **before** anything is persisted.
- **Lifecycle jobs** (`strata sweep`): confidence decay with per-type
  half-lives, page consolidation (bodies regenerated from the ledger — no
  append-rot), retention (`retain_days` per type), and lint (broken links,
  unsourced claims, injection content, ledger/prose drift).
- **An eval harness in the box.** `strata eval` synthesizes Q/A cases from your
  own supersession history and scores hit@k, current-fact rate, and stale-leak
  rate against your live config. Results are committed to `evals/`.
- **Portable by construction.** `strata export --to jsonl|mem0|memory-md`,
  `strata import --from jsonl|mem0`. Format contract: [STRATA-FORMAT.md](STRATA-FORMAT.md).

## Install

```bash
pip install -e .              # core: pure Python + git; heuristic extractor, FTS5 search
pip install -e .[llm]         # + Claude extraction (set ANTHROPIC_API_KEY)
pip install -e .[vector]      # + model2vec embeddings + sqlite-vec (hybrid L2 search)
pip install -e .[mcp]         # + MCP server for Claude Code/Desktop
pip install -e .[pii]         # + Presidio PII scanner
```

Everything degrades gracefully: no API key → offline heuristic extractor; no
vector extras → lexical BM25 only. The core never imports torch.

## The API (Mem0-shaped)

| Method | Notes |
|---|---|
| `add(messages, user_id, agent_id, run_id, metadata)` | ms-latency enqueue; PII gate; raises on `block` policy |
| `search(query, user_id, top_k, as_of, format="context")` | tiered: standing context → BM25 → RRF hybrid; packed-context mode |
| `get(id)` / `get_all(user_id, type, agent_id, run_id)` | full page dicts incl. claim ledger |
| `update(id, text)` | human correction → `human_edited` claim, committed |
| `delete(id, hard=False)` / `delete_all(user_id, hard=False)` | soft = archive; hard = path erasure |
| `history(id, include_diff=True)` | literally `git log --follow` on the page |
| `forget(user_id, mode="scrub"\|"rewrite")` | compliance erasure + tombstone |
| `flush()` / `reset()` / `stats()` / `maintenance()` / `lint()` | plumbing & lifecycle |
| `AsyncMemory` | same surface, `await`-able |

CLI: `strata init · ingest · search · list · read · history · review · forget ·
merge-users · sweep · lint · eval · stats · doctor · reindex · export · import ·
claim · serve` (MCP).

## Honest numbers (this machine: Windows 11, commodity CPU, 1K pages)

| op | p50 | p95 |
|---|---|---|
| `add()` enqueue | 6.3 ms | 9.1 ms |
| `search()` lexical | 8.0 ms | 12.2 ms |
| `search(format="context")` | 11.1 ms | 12.5 ms |

Reproduce: `python benchmarks/bench.py 1000`. NTFS file creation dominates
`add()`; Linux numbers are lower. Compilation (extract → resolve → one git
commit per batch) runs off the hot path at ~7 entries/s end-to-end on this
machine — git subprocess commits are the ceiling there.

## Known limitations (by design, documented per §13 of the research report)

1. **Eventual consistency** of compiled memory — the compat story with Mem0 is
   "same shape", not "same semantics". Raw-FTS + `flush()` bridge the gap.
2. **Offline heuristic extractor is a floor, not a feature** — first-person
   pattern matching only. Set an API key (or add an Ollama extractor behind the
   same Protocol) for real compilation.
3. **`scrub` erasure keeps git history** — that's the audit-friendly mode.
   Provable erasure is `--rewrite` (requires git-filter-repo, invalidates
   clones) — the tension is inherent (GDPR vs. audit trails), so both modes
   are explicit.
4. **Page-count ceiling ~50–100K per repo** — many small files is git's and
   NTFS's worst case. Beyond that, this architecture is the wrong tool.
5. **FTS5 porter stemming is English-biased**; model2vec trails full
   transformers, especially multilingual.

## Layout

```
strata/
├── memory.py            # Memory / AsyncMemory — the front door
├── models.py            # Page, Claim, PageOp, RawEntry, SearchHit (pydantic)
├── schema.py, config.py # schema.md ontology · config.yaml knobs
├── storage/             # repo IO · git backend · erasure/identity
├── write/               # queue+worker · extractors · ledger resolve · PII · review
├── read/                # FTS5 · tiered search+RRF · vectors (opt) · context packer
├── lifecycle/           # decay · consolidate · retention · lint
├── interop/             # jsonl · mem0 · MEMORY.md
├── evals/               # domain-eval harness
├── cli.py, mcp_server.py
└── templates/           # schema.md, config.yaml
```

## Try it

```bash
pip install -r requirements.txt && pip install -e .

streamlit run chatbot/app.py            # chat UI (Nemotron via NVIDIA_API_KEY in .env;
                                        # runs in labelled demo mode without a key)
python examples/simple_chatbot.py       # minimal integration loop, fully offline
pytest -q                               # 133 tests
```

## Benchmarks

```bash
python benchmarks/bench.py 1000                          # latency @1K pages
python -m benchmarks.memory_evals.run --self-test        # LoCoMo/LongMemEval/in-house on fixtures
python -m benchmarks.memory_evals.run --download-locomo --limit 2 --with-llm
python -m benchmarks.memory_evals.run --inhouse-repo ./chat-memory
```

The memory-eval runner prints per-benchmark and combined labelled tables and
saves JSON to `benchmarks/results/`. Retrieval-only numbers are answer-presence
recall proxies — not leaderboard-comparable (it says so in its own output).

Full architecture, implementation-status matrix, and the placeholder/mock
audit: [PROJECT-STATE.md](PROJECT-STATE.md).
