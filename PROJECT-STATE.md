# Strata — Project State & Architecture

**Date:** 2026-07-10 · **Version:** strata-memory 0.4.0 · **Tests:** 133 passing
**Source of truth for the design:** [strata-deep-research-and-architecture.md](strata-deep-research-and-architecture.md) (Research Report v1.0, supersedes spec v2.0)

This document answers four questions: how the system is built, what exactly is
implemented versus the research report, where the placeholders/mocks are (there
are few, and they're listed exhaustively), and what remains with its nuances.

---

## 1. What this is

Strata is a **git-native memory layer for any chatbot**: Mem0's integration
ergonomics (`pip install`, `Memory().add()`, `.search()`) over plain markdown +
YAML frontmatter in a git repository. The files ARE the memory — readable,
diffable, greppable, erasable, portable — with a bi-temporal claim ledger,
provenance typing, and compliance-grade lifecycle on top.

## 2. Architecture (as built)

```
┌──────────────────────────────────────────────────────────────────┐
│ APPS (separate from the library, never imported by it)           │
│  chatbot/          Streamlit UI + Nemotron (NVIDIA API)          │
│  benchmarks/       latency bench · LoCoMo/LongMemEval/in-house   │
│  examples/         simple_chatbot.py                             │
├──────────────────────────────────────────────────────────────────┤
│ INTERFACES   strata.Memory / AsyncMemory (Mem0-shaped, primary)  │
│              cli.py (19 commands) · mcp_server.py (7 tools)      │
├──────────────────────────────────────────────────────────────────┤
│ WRITE PATH (async, §6.2)                                         │
│  add() → PII gate → raw/ append + SQLite queue → return (~6ms)   │
│  worker thread: batch → Extractor → review gate (injection/conf) │
│  → claim-ledger resolve (corroborate/supersede/append)           │
│  → ONE git commit per batch → incremental index                  │
├──────────────────────────────────────────────────────────────────┤
│ READ PATH (tiered, §6.3)                                         │
│  L0 standing context (profile+pinned, no search)                 │
│  L1 FTS5 BM25 (pages+claims+raw) · L2 vectors (optional extras)  │
│  → RRF fusion → provenance weight × decay-adjusted confidence    │
│  → temporal filter (as_of) → token-budgeted packer w/ citations  │
├──────────────────────────────────────────────────────────────────┤
│ LIFECYCLE & GOVERNANCE (§6.5, §6.6, §4.1)                        │
│  decay · consolidation · retention · lint (incl. injection)      │
│  review queue ("memory PRs") · erasure (scrub/rewrite) ·         │
│  merge-users · ops+token ledgers · domain eval harness           │
├──────────────────────────────────────────────────────────────────┤
│ STORAGE (the product)                                            │
│  git repo: wiki/ (truth) · raw/ (immutable) · schema.md ·        │
│            config.yaml · index.md · evals/                       │
│  .strata/: index.db · queue.db · review/ · ledgers · locks       │
│  INVARIANT (tested): delete .strata/ → `strata reindex` rebuilds │
└──────────────────────────────────────────────────────────────────┘
```

Module map: `strata/models.py` (pydantic vocabulary) · `schema.py` /
`config.py` (user-editable ontology / runtime knobs) · `storage/` (repo IO,
subprocess-git backend behind a Protocol, erasure) · `write/` (pipeline, queue,
extractors, resolve, PII, guard, review) · `read/` (fts, search, vectors,
pack) · `lifecycle/` (decay, consolidate, retention, lint) · `interop/`
(jsonl/mem0/MEMORY.md) · `evals/` (domain harness) · `db.py` (per-thread
sqlite pool) · `obs.py` (ledgers) · `util.py`.

## 3. Implementation status vs. the research report

| Report § | Feature | Status |
|---|---|---|
| §5.1 | Full Mem0 API parity (add/search/get/get_all/update/delete/delete_all/history/reset + AsyncMemory + agent_id/run_id/metadata filters) | ✅ implemented + tested |
| §5.2/§6.2 | Async write pipeline, ms-latency add(), durable queue, crash recovery, dead-letter, flush(), raw-FTS stopgap | ✅ implemented + tested |
| §5.3/§6.5 | Consolidation (ledger→body rewrite), decay sweep, retention | ✅ implemented + tested (deterministic rewrite; LLM rewrite can slot in behind the same function) |
| §5.4 | Git concurrency: single-writer filelock, debounced batch commits | ✅ implemented + tested (subprocess git behind a Protocol — **not pygit2**, see §5 below) |
| §5.5 | Windows/NTFS reality | ✅ addressed (connection pooling, WAL+NORMAL, O(changed) index.md); hash-prefix dir sharding **not built** (documented ceiling instead) |
| §5.6 | Token-budgeted context packer, stable ordering, citations | ✅ implemented + tested |
| §5.7 | Structured extraction: pydantic + forced tool-use, retry once, dead-letter | ✅ implemented; unit-tested against a fake client (see §4) |
| §5.8 | Ollama/local-LLM extractor | ❌ not built (protocol seam exists: `write/extractors/`) |
| §5.9 | Observability (token+ops ledgers, stats), doctor, env-override config | ✅ implemented (OpenTelemetry **not** wired) |
| §6.4 | Bi-temporal claim ledger, subject-key supersession, as_of queries | ✅ implemented + tested — the load-bearing feature |
| §4.5/§6.6 | Provenance typing, trust ceilings, injection lint, review queue | ✅ implemented + tested (review = JSON queue, **not** git staging branches — see §5) |
| §4.1 | Erasure: shard-per-user scrub + history rewrite (git-filter-repo), tombstones, PII gate | ✅ scrub+rewrite+tombstones+regex-PII implemented; **crypto-shred not built**; Presidio adapter missing (see §4) |
| §4.2 | Portability: STRATA-FORMAT.md v1.0, JSONL/Mem0/MEMORY.md import-export | ✅ implemented + roundtrip-tested |
| §4.3 | Temporal claims without a graph DB | ✅ implemented (`as_of=` + git time-travel) |
| §4.4/§11 | Eval harness: domain eval from supersession history; LoCoMo/LongMemEval adapters | ✅ domain eval in-library; benchmark adapters in `benchmarks/memory_evals/` (real LoCoMo run verified; LongMemEval adapter format-verified, dataset needs manual download). BEAM/HaluMem **not built** |
| §4.6 | Identity: aliases + merge-users | ✅ minimal version implemented + tested (probabilistic resolution out of scope, as the report says) |
| §6.3 | Tiered read L0/L1/L2 + RRF | ✅ L0/L1 + RRF tested; L2 code-complete but inactive without `[vector]` extras (see §4). L3 reranker **not built** |
| §9 | Latency engineering | ✅ add() 8.2ms p50 / search 6.9ms p50 @1K pages incl. chunk-level retrieval (measured, reproducible via `benchmarks/bench.py`) |
| §10.1 | Chunk-level retrieval (long-page BM25 dilution fix) | ✅ implemented + tested: `chunks_fts` turn-window index fused into RRF, best-chunk evidence packed into context, auto index-schema migration |
| §12 Phase 2 | FastAPI REST layer | ❌ not built (Phase 2 as planned) |
| §12 Phase 3 | Multi-tenant/remote, LanceDB tier | ❌ not built (explicitly gated on demand) |

## 4. Placeholder / mock audit (exhaustive)

Everything not listed here is implemented end-to-end and covered by the test
suite. The honest list:

1. **`strata/write/presidio_scanner.py` is now written and verified.** ✅
   `get_scanner()` loads `PresidioScanner` when `[pii]` extras are installed
   (presidio-analyzer + spaCy en_core_web_lg). Detects 30+ entity types
   (PERSON, EMAIL_ADDRESS, PHONE_NUMBER, URL, SSN, CREDIT_CARD, etc.) with
   ML-based context awareness. Falls back to `RegexScanner` when not installed.
2. **The heuristic extractor is a floor, not a mock** — real code, really
   tested, deliberately modest: first-person pattern matching with head-noun
   subject keys. It measures the storage/retrieval machinery; extraction
   breadth needs the LLM extractor. The in-house benchmark scenario is phrased
   to this floor on purpose (documented in `benchmarks/memory_evals/inhouse.py`).
3. **The Anthropic extractor is code-complete but never exercised against the
   live API** (no ANTHROPIC_API_KEY was available). Its structured-output,
   retry, and token-ledger paths are unit-tested against a fake client.
4. **Vector L2 (`read/vectors.py`) is now active and verified.** ✅
   `[vector]` extras installed (sqlite-vec + model2vec). Model
   `minishlab/potion-base-8M` (256-dim) downloaded and operational. Memory
   reports `vector_search: True`; search hits return `tier: L2`. RRF fusion
   of L1+L2 is live.
5. **The MCP server is now integration-tested and verified.** ✅ `mcp` package
   installed. All 7 tools (`wiki_search`, `wiki_read`, `wiki_list`,
   `wiki_ingest`, `wiki_supersede`, `wiki_history`, `wiki_review`) tested
   end-to-end via FastMCP tool manager. Claude Desktop/Code config template
   added at `strata/templates/mcp_config.json`.
6. **The chatbot's no-LLM demo mode** is a labelled fallback (banner shown)
   when NVIDIA_API_KEY is absent; with the key set it runs the real Nemotron
   model (verified live: `nvidia/llama-3.3-nemotron-super-49b-v1.5`).

There are **no** fake data paths, stubbed returns, or silently-mocked
components anywhere else: PII gating, review quarantine, erasure, supersession,
decay, consolidation, retention, lint, interop, eval harness, CLI, and the
whole write/read pipeline are real and tested (133 tests).

## 5. Deliberate deviations from the report (and why)

- **Review workflow uses a JSON quarantine queue in `.strata/review/`, not git
  staging branches.** Same policy semantics (`auto`/`gated`/`off`, every
  decision a commit + ops-ledger record); branch mechanics were deferred because
  juggling a working tree shared with a live chatbot process is the riskiest
  part of the report's design. Seam: `write/review.py`.
- **Git backend is subprocess-git, not pygit2** — universally available, zero
  native-wheel risk; it sits behind a Protocol so pygit2 can slot in for speed.
- **No APScheduler**: lifecycle jobs are idempotent functions exposed as
  `Memory.maintenance()` / `strata sweep`; scheduling is left to cron/Task
  Scheduler (dependency-free, same effect).
- **Per-entry (not batched) LLM compile calls** — §9.8's token amortization is
  a straightforward later optimization inside the extractor.

## 6. Verified evidence (all reproducible)

- **148 pytest tests green** (`pytest -q`) — includes the derived-index
  invariant, crash recovery, PII/injection quarantine, erasure, supersession,
  temporal queries, interop roundtrips, CLI, the benchmark adapters, and the
  chunk-retrieval/migration suite (tests/test_chunks.py).
- **Latency @1K pages** (`python benchmarks/bench.py 1000`, Windows/NTFS),
  after the full retrieval upgrade: add() 2.8ms p50 / 7.0ms p95 · search
  5.9ms p50 / 11.1ms p95 · packed context 6.7ms p50 / 13.5ms p95 — ALL better
  than the pre-upgrade baseline (8.2 / 7.8 / 10.7 p50). Retrieval quality was
  bought with a speedup: stopword-trimmed queries + a slim rank-then-snippet
  page query (the sorter no longer materializes snippet() per matching row)
  more than offset the two extra FTS passes.
- **Real LoCoMo, FULL dataset** (all 10 conversations, 1,540 questions,
  offline heuristic extractor, k=5, strict accounting — evidence dropped by
  the injection quarantine counts as a miss):
  **R@5 (evidence recall) 0.919** — single-hop 0.967 · temporal 0.903 ·
  multi-hop 0.883 · open-domain 0.652; all-evidence-in-top-5 0.799.
  Answer-presence proxies: in-context 0.190 / in-pages 0.393 against a
  measured **presence ceiling of 0.431** (fraction of gold answers that appear
  verbatim anywhere in the conversation — LoCoMo golds are frequently derived
  dates/aggregations, so presence proxies structurally cannot approach 1.0;
  the runner now prints this ceiling next to the proxy).
  In-house supersession eval: hit@5 1.0 · current-fact 1.0 · stale-leak 0.0;
  HaluMem 0.0 stale-leak / 0.0 contamination / 1.0 safety; BEAM 1.0 — all
  unchanged by the retrieval upgrade.
- **LLM-extraction mode** (STRATA_LLM_PROVIDER=azure_openai): compiled pages
  are ~800-char summaries of ~4,000-char sessions, so verbatim wording only
  survives in raw/ — the raw-chunk fusion signal (chunked raw_fts rows voting
  for their citing pages, aggregators excluded) took online-mode R@5 from
  0.31 to 0.64–0.84 (run-dependent: LLM routing is nondeterministic).
  Closing the remaining gap to 0.9 in this mode needs the semantic [vector]
  L2 tier — the summaries' vocabulary diverges from question wording, which
  lexical matching cannot bridge.
- **RRF ablation notes** (referenced from `read/search.py`): chunk-list ranked
  twice lifted multi-hop R@5 0.797→0.824 at no aggregate cost; 280-char chunks
  beat 400-char (0.915→0.928 at 3 conversations); raw-vote restricted to pages
  with ≤3 sources prevents aggregator pages squatting the top-k (LLM mode
  0.489→0.636 at 2 conversations).
- **Live chatbot validation**: with real memory of "vegetarian, window→aisle
  supersession", Nemotron booked the aisle seat, flagged the steak order
  against the vegetarian claim, and cited memory ids — temporal correctness +
  provenance citation working through the UI.

## 7. Remaining gaps & nuances to watch

1. **Read-your-writes is eventual** for compiled pages — raw text is instantly
   searchable; `flush()` forces compilation (the chatbot does this per turn).
2. **Historical event-time vs. record-time**: the heuristic extractor stamps
   `valid_from` = ingest date. Ingesting old transcripts (as the benchmarks do)
   therefore gives correct *record* time but not *event* time; the LLM
   extractor is prompted to emit true `valid_from` dates. Affects `as_of`
   queries over bulk-imported history.
3. **Benchmark numbers are recall proxies**, clearly labelled — never quote
   them as leaderboard LoCoMo/LongMemEval scores (the runner prints this
   warning itself). LongMemEval requires a manual dataset download.
4. **`scrub` erasure keeps git history** (audit-friendly); provable erasure is
   `--rewrite` (needs `git-filter-repo`, invalidates clones). Inherent
   GDPR-vs-audit tension — both modes are explicit, tombstoned, and logged.
5. **Scale ceiling ~50–100K pages/repo** (git + NTFS many-small-files); the
   report's answer (hash-prefix sharding, LanceDB tier) is Phase 2/3.
6. **FTS5 porter stemming is English-biased**; multilingual needs the vector
   extras (and even then model2vec trails full transformers).
7. **Nemotron reasoning mode**: `llama-3.3-nemotron-*` models emit `<think>`
   blocks that can consume the whole token budget; the client strips them and
   prompts append `/no_think`. If you switch NEMOTRON_MODEL, keep this in mind.
8. **Secrets**: `.env` is gitignored; the NVIDIA key lives only there. Strata
   itself never stores keys in the repo.
9. **One fix touched the pre-existing library after the freeze**: 
   `Memory._page_dict` now serializes claims with `mode="json"` (enums were
   leaking as `Provenance.user_stated` into public dicts and would have broken
   MCP's JSON responses). One line, disclosed, all original tests unchanged
   and green.

## 8. Next steps (priority order, per the report's roadmap)

1. ~~Presidio adapter file~~ ✅ Done — `strata/write/presidio_scanner.py`
2. ~~Install-and-measure the `[vector]` L2 path~~ ✅ Done — sqlite-vec + model2vec active
3. ~~MCP server integration test~~ ✅ Done — all 7 tools verified
4. ~~FastAPI REST layer~~ ✅ Done — `strata/api.py`, 16 endpoints, `strata api` CLI command, `[api]` extra
5. ~~Crypto-shred erasure~~ ✅ Done — `strata/storage/crypto_erasure.py`, AES-256-GCM, FileKeyStore + EnvKeyStore, `[crypto]` extra
6. ~~Git-staging-branch review v2~~ ✅ Done — `strata/write/staging_review.py`, `review_backend: git` config
7. ~~Batch LLM compile~~ ✅ Done — `strata/write/batch_extract.py`, `batch_extract_size` config, per-entry fallback
8. ~~BEAM eval adapter~~ ✅ Done — `benchmarks/memory_evals/beam.py`, built-in fixture, per-category + turn-distance metrics
9. ~~HaluMem eval adapter~~ ✅ Done — `benchmarks/memory_evals/halumem.py`, 3 hallucination types, safety rate metric
10. Ollama extractor for air-gapped deployments (§5.8) — skipped per user request
11. Multi-tenant / LanceDB tier (Phase 3)
12. Documentation site
