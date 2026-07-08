# Strata — Deep Research, Gap Analysis & Revised Architecture

### Research Report v1.0 — input to Spec v3.0

**Date:** 2026-07-06
**Input:** `strata-memory-spec.md` (Implementation Specification v2.0)
**Method:** Web research against the live mid-2026 market (all sources listed in Appendix A; vendor-self-reported numbers are flagged as such), cross-checked against the claims in spec v2.0.
**Verdict up front:** The core bet is still sound, but one competitor development (Letta's git-backed Context Repositories, Feb 2026) forces a sharper positioning, and the biggest *validated* market gaps — compliance-grade erasure + audit, memory portability, memory trust/provenance, and application-level evaluation — are not yet in the spec at all. This document proposes how to own them with a fully open-source stack.

---

## 1. Executive Summary

1. **The spec's market table is directionally right but stale.** Mem0 is now ~58.4K★ (was 48K), agentmemory has doubled to 20K+★, Graphiti crossed 20K★ with 25K weekly PyPI downloads. All spec numbers should be refreshed before external use (§2).
2. **The biggest new threat:** Letta shipped **Context Repositories** (Feb 2026) — agent memory projected onto the local filesystem as plain files, **git-versioned, with commit messages and branch/merge for subagents**. "Git-native memory" is no longer unclaimed territory. What remains open: Letta's version is coupled to the Letta runtime and Letta Code (a coding agent); nobody offers *a runtime-free Python library with a Mem0-shaped API over git+markdown* (§2.2, §4.1).
3. **The most valuable validated gaps are compliance and portability, not retrieval quality.** Mem0's own 2026 state-of-memory report lists privacy/consent frameworks, cross-session evolution, application-level evaluation, and identity resolution as unsolved. Independent governance research adds: *no vector database offers provable deletion*, GDPR erasure conflicts with the EU AI Act's audit-trail requirements (fully applicable **August 2026**), and there is **no standard portable memory format** across the five major frameworks (80K+ combined stars). Git+markdown is uniquely positioned to answer all of these (§4).
4. **Retrieval accuracy is table stakes you can reach cheaply:** FTS5 BM25 + small local embeddings + RRF + a 149M-parameter open reranker reproduces the "hybrid + rerank" pattern the leaders (Hindsight, agentmemory) use, entirely offline (§8, §10).
5. **Latency is won at the write path, not the read path.** `add()` must return in milliseconds (append raw + enqueue), with LLM compilation running asynchronously — the same insight behind Letta's sleep-time compute and Mem0's async mode. The spec's current synchronous ingest is its single biggest architectural flaw (§5.2, §9).
6. **Add a temporal claim model.** Bi-temporal fields (`valid_from`/`valid_until`/`recorded_at`) in frontmatter give Zep-style "what was true at time T" without a graph database — and directly target the "cross-session evolution" gap Mem0 admits it hasn't solved (§4.3, §6.4).
7. **Memory trust is an emerging, underserved axis:** memory poisoning/contamination (MemGuard), provenance typing (arXiv work on provenance-role collapse), and zero-trust memory (MemTrust) are active research with no mainstream OSS implementation. Typed provenance + a review workflow ("memory PRs" — unique to git storage) is a cheap, differentiating answer (§4.5, §6.6).
8. **Ship an eval harness as a feature, not a chore.** "Application-level evaluation" is a named gap in the market leader's own report; `strata eval` scaffolding domain-specific memory evals would be a first (§11).
9. **The revised stack stays boring:** stdlib SQLite FTS5, `sqlite-vec`, `model2vec`/`fastembed`, `rerankers`, `presidio`, `pygit2`, `pydantic`, `typer`, `FastMCP`, `FastAPI` — every layer swappable behind a Protocol, nothing requiring a server process (§8).
10. **Roadmap change:** insert a "Phase 0.5 — hardening" (async write path, API parity, git concurrency) before the spec's Phase 1, and pull compliance features (erasure modes, PII hook, audit) forward from "never mentioned" to Phase 1–2, because that is the wedge (§12).

---

## 2. Fact-Check: Spec v2.0 vs. the Market as of July 2026

### 2.1 Claim-by-claim

| Spec v2.0 claim | Status July 2026 | Impact |
|---|---|---|
| Mem0 ~48K★, $249/mo Pro | **Outdated.** ~58.4K★ (June 2026); pricing now Hobby free (10K memories) / Starter $19 / **Growth $79 (new tier)** / Pro $249. Still AWS Agent SDK's memory provider. Shipped a new single-pass hierarchical extraction algorithm (Apr 2026): self-reported 92.5 LoCoMo, 94.4 LongMemEval at ~6.9K tokens/query, +29.6 on temporal, +23.1 on multi-hop. Also ships **OpenMemory**, a local-first MCP memory server. | The "local-first" flank is no longer uncontested — OpenMemory exists. But OpenMemory is still a database-backed MCP server, not readable files. Positioning holds; sharpen it (§4.1). |
| agentmemory 11.6K★, 51 MCP tools | **Outdated.** 20K+★, **53 tools**, 6 lifecycle hooks, SHA-256 dedup, privacy filtering, hybrid BM25+vector, 6 embedding providers. Author published "LLM Wiki v2" lessons-learned gist. | Momentum is real. Do exactly what the spec says: read it before building past Phase 0 — and read the LLM Wiki v2 gist too. |
| Zep/Graphiti "mostly SaaS now" | Graphiti core remains open and is growing fast: 20K★, 25K weekly PyPI downloads. Zep self-reports 94.7 LoCoMo / 90.2 LongMemEval. | Unchanged: don't fight them on temporal graphs. But steal the *idea* of validity windows cheaply (§6.4). |
| Letta = runtime with tiered memory | **Materially changed.** Letta shipped **sleep-time compute** (async memory processing during idle time) and, in **Feb 2026, Context Repositories / MemFS**: agent memory projected onto the local filesystem as plain files, git-backed, auto-committed with informative messages, with branch/merge used to manage divergence between concurrent subagents. | **This is the single most important market change since spec v2.0.** See §2.2. |
| LongMemEval + LoCoMo are the benchmarks | Still true, plus two new ones: **BEAM** (long-horizon: SOTA only 64.1 at 1M tokens, 48.6 at 10M — everyone degrades at scale) and **HaluMem** (memory hallucination; EverMind self-reports 93.04). | Add BEAM + HaluMem to the eval plan (§11). |
| "The wiki/graph is never the primary storage" (§2.2 of spec) | **Now only mostly true.** Letta's Context Repositories make files the storage — but only inside the Letta runtime, and marketed for coding agents. Mem0/Zep/Cognee/agentmemory unchanged (DB or custom engine primary). | The gap narrows from "nobody does files-as-truth" to "nobody does files-as-truth **as an embeddable, runtime-free library with a Mem0-shaped API**." Still real, but the window is closing — Letta proved the concept has legs, which invites fast-followers. |
| Claude Code native memory validates index-first pattern | Still true; unchanged. | Keep `index.md` design. |

### 2.2 The Letta problem, and why the bet survives it

Letta's [Context Repositories](https://www.letta.com/blog/context-repositories/) is git-native memory done seriously: files as primitives, automatic versioned commits, subagent collaboration through branches and merges. Three things keep Strata viable:

1. **Adoption model.** Letta requires adopting Letta — a server, an agent runtime, their abstractions. Strata's target user has an existing chatbot on OpenAI/Anthropic/LangChain and wants `pip install` + two method calls. That's Mem0's adoption model, which is precisely why Mem0 has 3× Letta's mindshare.
2. **Audience.** Context Repositories is positioned for *coding agents managing their own context*. Strata is memory *about end-users of an application*, with `user_id` scoping, compliance controls, and a compilation pipeline. Different job.
3. **The compliance/portability wedge (§4) is orthogonal** — Letta hasn't touched provable erasure, PII controls, consent, or a portable interchange format either.

But take the warning: **the "git-native" label alone is no longer a moat.** The moat must be *git-native + Mem0-ergonomics + compliance-grade lifecycle*, as a package.

---

## 3. Market Landscape (July 2026)

Categories, per the Graphlit survey, vectorize.io comparisons, and vendor materials (star counts approximate; benchmark numbers **vendor-self-reported unless noted**):

| Player | Category | Storage truth | Self-reported benchmarks | Notes |
|---|---|---|---|---|
| **Mem0** | Managed memory API + OSS library | Vector (+graph on Pro) DB | 92.5 LoCoMo / 94.4 LongMemEval @ ~6.9K tok/query | ~58.4K★; AWS Agent SDK provider; 21 framework + 20 vector-store integrations; OpenMemory local MCP server |
| **Zep / Graphiti** | Temporal knowledge graph | Graph DB (Neo4j/FalkorDB) | 94.7 LoCoMo / 90.2 LongMemEval | Validity windows per fact; Graphiti OSS 20K★; claims up to 90% latency reduction vs full-context |
| **Letta** | Stateful agent runtime | Postgres + files (MemFS/Context Repos) | — | Memory blocks, sleep-time compute, git-backed Context Repos (Feb 2026) |
| **agentmemory** | Coding-agent memory engine (MCP) | Custom "iii engine" | claims #1 on "real-world benchmarks" | 20K+★, 53 tools, hybrid search, lifecycle hooks; closest prior art to Strata's compile pipeline |
| **Hindsight** | OSS memory framework | DB | Leads on *public* benchmark visibility | 4 parallel retrieval strategies (semantic, BM25, graph, temporal) + cross-encoder rerank — the pattern to reproduce cheaply |
| **EverMind** | Personalization memory | DB | 93.05 LoCoMo / 83.0 LongMemEval / 93.04 HaluMem | Aggressive content marketing; deep personalization focus |
| **Cognee** | Enterprise graph memory | Graph + vector | — | ECL pipeline; positioning toward governed, cited enterprise knowledge |
| **LangMem** | LangGraph-native memory | LangGraph store | — | Best only if you're already on LangGraph |
| **Supermemory** | Managed memory API | DB | Publishes useful latency-budget engineering material | See §9 |
| **claude-mem / OpenMemory / MemPalace** | Local-first session capture | SQLite/Chroma | — | Validates local-first demand; all flat/opaque storage |
| **Memvid** | Embedded retrieval engine | Files + Tantivy BM25 + HNSW | — | Technical reference for the retrieval stack: Tantivy + ONNX embeddings + RRF |

**Academic signals worth tracking** (all 2026 arXiv): *Portable Agent Memory* (provenance-verified memory transfer protocol across heterogeneous agents), *MemGuard* (preventing memory contamination), *MemTrust* (zero-trust memory architecture), *PROJECTMEM* (local-first, event-sourced memory for coding agents — independent validation of Strata-like design), and work on typed memory representations to prevent "provenance-role collapse." None have mainstream OSS implementations yet — that's a shopping list for differentiation.

---

## 4. The Gaps Nobody Fills — Strata's Wedge

These are not speculative: gaps 1–4 below come from **Mem0's own 2026 state-of-memory report** plus independent governance research; gap 5 from the interoperability literature. Ranked by how credibly a git+markdown architecture can own each.

### 4.1 Compliance-grade memory: provable erasure *and* provable audit (own this)

The documented situation:

- **No commercially available vector database provides a provable deletion mechanism** for embedded data — a live GDPR compliance gap (governance research, Atlan/VerityAI).
- The **EU AI Act (fully applicable August 2026)** requires ~10-year audit trails for high-risk systems, which *structurally conflicts* with GDPR's right to erasure. Every memory vendor punts on this.
- Multi-agent context handoff moves PII between agents **with no audit at the transfer point**.

Git+markdown can uniquely answer both sides — but note the tension honestly: **git's history is itself an erasure problem** (deleted files persist in history). Ship three explicit, documented erasure modes:

| Mode | Mechanism | Erasure guarantee | Audit guarantee | Cost |
|---|---|---|---|---|
| **Shard-per-user** (recommended default for multi-user) | Each `user_id` gets its own sub-repo (or orphan branch); `strata forget --user X` deletes the whole shard + `git gc --prune=now` | Strong, simple, provable | Per-user history until erasure; tombstone record of the erasure event kept in an ops log | Slightly more complex repo layout |
| **History rewrite** | `git-filter-repo` removes a path/user from all history, then aggressive gc | Strong (with documented caveats: clones/remotes must be rotated) | Weakened for rewritten paths | Slow on big repos; invalidates clones |
| **Crypto-shredding** (optional, regulated deployments) | User-scoped page bodies encrypted at rest with per-user keys (`cryptography` lib, keys in OS keyring); erasure = key destruction | Strong, instant, works across all backups | Full — ciphertext history remains as tamper-evident audit trail | **Sacrifices human-greppability** for those pages — offer it, don't default it |

Plus: `git log` **is** the audit trail (who/what/when for every memory mutation — signed commits give tamper-evidence for free), and a **Presidio-based PII gate** on the ingest pipeline (detect → tag / mask / block per policy in `schema.md`) covers the "PII enters at the context layer" finding. Retention policy (`retain_days` per page type) enforced by the same sweep job as decay.

**No incumbent offers this as a coherent package.** It converts "markdown+git" from an aesthetic preference into a regulated-industry requirement — which is exactly the audience §4 of the spec already targets.

### 4.2 Portable memory format (own this, cheaply)

The interoperability literature is blunt: five major frameworks, 80K+ combined stars, **no standard schema for what a "memory" is**; switching providers means losing history. An arXiv proposal (*Portable Agent Memory*) exists but has no reference implementation.

Strata's storage *is* a portable format — human-readable markdown + YAML frontmatter in a repo. Lean in:

- Publish the frontmatter schema as a versioned spec (`STRATA-FORMAT.md`), semantic-versioned, with a JSON Schema for validation.
- Ship `strata import --from mem0|zep|jsonl|memory-md` and `strata export --to mem0|jsonl|memory-md` from Phase 1. Import from Mem0's export is the highest-leverage distribution channel: *"leave Mem0 without losing your memory."*
- Track the Portable Agent Memory proposal; align field names where free.

### 4.3 Cross-session evolution / temporal claims without a graph DB (adopt the idea, skip the engine)

Mem0's report names "cross-session evolution — systems replace facts rather than model how circumstances change" as unsolved; Zep solves it with a full temporal graph. The 80/20 version needs no graph database: **bi-temporal claim records** in frontmatter (§6.4) — `valid_from`, `valid_until`, `recorded_at`, `supersedes`. Queries like "what did we believe on May 1" become a frontmatter filter, answerable from SQLite. Combined with `git log` (which gives *record*-time travel for free), Strata gets both timelines of bi-temporality with zero new infrastructure — a genuinely defensible story: *"time-travel your memory with `git checkout`, time-travel your facts with `valid_from`."*

### 4.4 Application-level evaluation (own this — nobody has)

Mem0's report: benchmarks measure general recall, not domain performance. No framework ships eval tooling for *your* memory. `strata eval` (§11) — a harness that (a) runs LoCoMo/LongMemEval/BEAM subsets against your live config, and (b) scaffolds a domain eval from your own repo's history (auto-generate Q/A pairs from superseded claims: "what is X's current seat preference?" with ground truth from the claim ledger) — is cheap to build on the claim model and instantly quotable: *"the only memory layer that ships its own eval harness."*

### 4.5 Memory trust: provenance typing + poisoning defense (differentiate)

Active research (MemGuard, MemTrust, provenance-role collapse), zero mainstream OSS implementation. Memory is an **injection surface**: a malicious or manipulated conversation can plant instructions that get compiled into pages and re-injected into every future prompt. Cheap, concrete defenses:

- **Typed provenance on every claim:** `user_stated | agent_inferred | tool_derived | imported | human_edited`, set by the compiler, surfaced in search results. Never let inferred claims masquerade as user statements (this is exactly the "provenance-role collapse" failure).
- **Trust ceilings by provenance** in `schema.md` (e.g., `imported` caps at confidence 0.6 until corroborated).
- **Injection lint:** compile-time check flagging imperative/instruction-shaped content in memory ("ignore previous instructions", tool-invocation syntax) for review instead of silent storage.
- **Memory PRs (unique to git):** agents write to a staging branch; policy auto-merges high-confidence, non-contradicting edits and queues the rest for `strata review` (a rich diff TUI). *No other memory product can offer human review of memory diffs as a native primitive.* This also answers the multi-agent handoff audit gap from §4.1.

### 4.6 Identity resolution (acknowledge, don't over-invest)

Named gap (anonymous sessions, multi-device users). Ship a minimal `aliases:` map on user pages + `strata merge-users A B` (git-mv + frontmatter rewrite + index rebuild). Full probabilistic identity resolution is out of scope — say so.

### 4.7 What NOT to chase (unchanged from spec, reaffirmed by data)

- 10M-token temporal abstraction (BEAM's hard frontier) — the funded labs' problem.
- Graph-benchmark leadership vs Zep.
- Beating Mem0's self-reported LoCoMo score as a headline. Compete on *properties* (ownership, auditability, erasure, portability, reviewability), publish honest benchmark numbers as "competitive, at zero cloud cost."

---

## 5. Critique of Spec v2.0 — Concrete Improvements

### 5.1 API parity gaps (adoption blockers)

The Mem0-shaped API is the product's front door; today it's missing too much of Mem0's actual surface. Required for the "change one import" pitch:

| Method | Status in spec | Action |
|---|---|---|
| `add()` / `search()` / `get()` / `get_all()` | ✅ built | Keep; add `agent_id`, `run_id`, `metadata` filters to `search()`/`get_all()` |
| `update(memory_id, data)` | ❌ missing | Phase 0.5 — maps to page edit + recompile + commit |
| `delete(memory_id)` / `delete_all(user_id)` | Repo-level only | Phase 0.5 — soft archive by default; `hard=True` invokes erasure modes (§4.1) |
| `history(memory_id)` | Repo-level only | Phase 0.5 — trivially better than Mem0's: it's `git log --follow -p` on the page |
| `reset()` | ❌ missing | Phase 0.5 |
| `AsyncMemory` | ❌ missing | Phase 1 — thin `asyncio` wrapper; table stakes for modern Python backends |
| Batch add | ❌ missing | Phase 1 — amortizes LLM compile cost |

### 5.2 The write path is synchronous — the biggest architectural flaw

Spec Phase 0 compiles (an LLM call, hundreds of ms to seconds) *inside* `add()`. Every production system (Letta sleep-time compute, Mem0 async mode) moved compilation off the hot path. Fix (§6.2): `add()` = append raw + enqueue + return (single-digit ms); a background worker (thread in-process by default; separate process optional) batches, compiles, writes, commits, reindexes. Consequence to embrace and document: **read-your-writes is eventual** for compiled pages (raw is immediately searchable via a raw-FTS table as a stopgap; `m.flush()` forces synchronous compilation for tests).

### 5.3 No page compaction — append-only pages will rot

Phase 0's "append a new `## Details (updated …)` section forever" bloats pages, degrades retrieval (BM25 dilution), and burns context tokens. Add a **consolidation job** (nightly or every-N-updates): LLM rewrites the page body from its claim ledger into clean prose, git preserving the pre-consolidation state. This mirrors agentmemory's 4-tier consolidation and Letta's sleep-time rewriting — it's the part of their designs worth copying.

### 5.4 Git concurrency is unaddressed

A chatbot backend runs multiple workers; concurrent `git commit` corrupts nothing but races produce lock errors and interleaved index states. Fix: single-writer discipline — all mutations flow through the ingest queue (§5.2 already forces this); `filelock` around commit; **debounced batch commits** (one commit per worker cycle, not per page write) keep history readable and fast. Use `pygit2` (libgit2) rather than shelling out; fall back to `dulwich` (pure Python) where libgit2 wheels are unavailable.

### 5.5 Filesystem reality check (especially Windows)

Many small files is git's worst case and NTFS's too. Mitigations: shard wiki dirs by 2-char hash prefix once a type exceeds ~1K pages; `core.fscache=true`, `core.untrackedCache=true` on Windows; periodic `git gc`; document a practical ceiling (~50–100K pages/repo) and the shard-per-user layout (§4.1) as the scale path. Benchmarks to publish honestly: p50/p95 search latency and ingest throughput at 1K / 10K / 100K pages.

### 5.6 Retrieval returns pages; prompts need budgeted context

The spec has `token_budget: 2000` in config but no packing strategy. Add a **context packer**: dedupe by page, order stable-first (user page → pinned → retrieved by score) so prompt-prefix caching works, truncate at claim boundaries, always attach `id` + `confidence` + provenance so the LLM can cite memory. Expose as `m.search(..., format="context")` returning a single packed string — this is what integrators actually paste into prompts.

### 5.7 Structured extraction needs structure

`LLMExtractor` returning "a JSON list of page operations" via prose prompting will produce malformed output at scale. Use **pydantic models + the Anthropic structured-outputs / tool-use path** (or `instructor` for provider-agnostic structured output; `litellm` if multi-provider LLM support is wanted without writing N adapters). Validation failures → retry once with the error message → dead-letter queue in `raw/failed/`, never silent drops.

### 5.8 The offline fallback should be a local model, not a keyword heuristic

"Deliberately low quality" offline mode undercuts the local-first pitch. Keep the heuristic as the zero-dependency floor, but add an **Ollama/llama.cpp extractor** (same `extract()` Protocol) so fully-offline deployments get real compilation. This matters to exactly the regulated/air-gapped audience §4 targets.

### 5.9 Missing entirely from the spec — add sections for

- **Security threat model** (memory poisoning/injection — §4.5).
- **Compliance & erasure** (§4.1).
- **Observability:** structured logs; optional OpenTelemetry spans around compile/search; a `strata stats` command (token spend per day, pages by type/status, compile failure rate, search latency histogram). "Track token spend from day one" appears in spec §15 as a risk — make it a feature.
- **Config/DX polish:** `pydantic-settings`-backed config with env-var overrides; JSON Schema for `config.yaml` + `schema.md` fenced block (editor autocomplete); `strata doctor` (checks FTS5 availability, git presence, key config).

---

## 6. Revised Architecture

### 6.1 Layered, plugin-first design

Everything above the storage line is a swappable plugin behind a Python `Protocol`; discovery via package entry points (`stevedore` or plain `importlib.metadata`). The core installs with **zero heavy dependencies**; extras pull in optional capability.

```
┌────────────────────────────────────────────────────────────────┐
│ INTERFACES        Memory / AsyncMemory (mem0-shaped, primary)  │
│                   CLI (typer) · MCP (FastMCP) · REST (FastAPI) │
├────────────────────────────────────────────────────────────────┤
│ SERVICES                                                       │
│  WritePipeline: gate(PII) → enqueue → extract → resolve        │
│                 (contradiction/supersede) → write → commit     │
│                 → index   [async worker, batched]              │
│  ReadPipeline:  route → candidate gen (FTS5 ∥ vector) → RRF    │
│                 → [rerank] → temporal filter → pack(budget)    │
│  Lifecycle:     decay sweep · consolidation · retention ·      │
│                 lint · eval   [scheduled jobs, APScheduler]    │
│  Governance:    erasure modes · review queue (memory PRs) ·    │
│                 audit (git log) · stats/otel                   │
├────────────────────────────────────────────────────────────────┤
│ PLUGIN PROTOCOLS (entry-point discoverable)                    │
│  Extractor      anthropic · openai-compat · ollama · heuristic │
│  Embedder       model2vec · fastembed · sentence-transformers  │
│  Reranker       none · rerankers[gte-modernbert] · API         │
│  VectorStore    none · sqlite-vec · lancedb                    │
│  PIIScanner     none · presidio                                │
│  GitBackend     pygit2 · dulwich · subprocess                  │
├────────────────────────────────────────────────────────────────┤
│ STORAGE (the product — no plugin above may bypass it)          │
│  git repo: raw/ (immutable) · wiki/*.md (truth) · schema.md    │
│            index.md · config.yaml                              │
│  .strata/: index.db (FTS5+vec, DERIVED) · queue.db · locks     │
│  invariant: delete .strata/ entirely → `strata reindex`        │
│             rebuilds everything from the markdown              │
└────────────────────────────────────────────────────────────────┘
```

Protocol sketch (the contract that keeps it modular):

```python
class Extractor(Protocol):
    def extract(self, raw: RawEntry, index_summary: str,
                schema: Schema) -> list[PageOp]: ...

class Embedder(Protocol):
    dim: int
    model_id: str                      # stored in index.db; mismatch → auto reembed
    def embed(self, texts: list[str]) -> list[list[float]]: ...

class VectorStore(Protocol):
    def upsert(self, ids: list[str], vecs: list[list[float]]) -> None: ...
    def query(self, vec: list[float], k: int,
              filter: dict | None = None) -> list[tuple[str, float]]: ...
```

### 6.2 Write path (async, staged)

```
add(msgs, user_id) ──► [PII gate] ──► raw/ append + queue row ──► return {queued_id}   (~1–5 ms)
                                            │
                        background worker (thread; batch N or T seconds)
                                            ▼
                    Extractor → PageOps → ContradictionResolver
                    (new claim vs existing claims on target page:
                     agree→confidence↑ · new→append claim ·
                     conflict→supersede or queue for review per policy)
                                            ▼
                    write pages (staging branch if review enabled)
                    → batched commit (pygit2) → incremental index update
```

### 6.3 Read path (tiered — pay only for what the query needs)

- **L0 — standing context:** the user's compiled `user/` page + pinned pages, served from cache, no search at all. Covers the most common personalization case at ~0 cost.
- **L1 — lexical:** FTS5 BM25 (already built). Sub-10ms.
- **L2 — hybrid:** local embeddings + sqlite-vec in parallel with L1, RRF fusion (rank-only, ~7 lines, no score calibration needed).
- **L3 — rerank:** top-20 fused → open cross-encoder → top-k. Optional flag.
- Then: temporal filter (default `valid_until IS NULL`; `as_of=` for point-in-time), status filter (exclude superseded/archived unless asked), context packer (§5.6).

### 6.4 The claim ledger (the key data-model upgrade)

Pages stay human-readable prose; frontmatter gains a machine-grade claim ledger the lifecycle and eval systems operate on:

```yaml
---
type: user
id: user/alice
# ... existing fields (confidence, status, sources, summary) ...
claims:
  - id: c-2026-07-06-a3f1
    text: "Prefers aisle seats"
    valid_from: "2026-07-06"
    valid_until: null
    recorded_at: "2026-07-06T09:02:00Z"
    confidence: 0.9
    provenance: user_stated        # user_stated|agent_inferred|tool_derived|imported|human_edited
    sources: [raw/conversations/2026-07-06T08-14-00__session-1.md]
    supersedes: c-2026-05-01-b2e0
  - id: c-2026-05-01-b2e0
    text: "Prefers window seats"
    valid_from: "2026-05-01"
    valid_until: "2026-07-06"      # closed by the claim above
    recorded_at: "2026-05-01T10:00:00Z"
    confidence: 0.9
    provenance: user_stated
    sources: [raw/conversations/2026-05-01T10-00-00__session-9.md]
---
Alice prefers aisle seats (changed from window seats in July 2026). …
```

This one structure powers: supersession (Phase 1), temporal queries (§4.3), provenance/trust (§4.5), auto-generated domain evals (§4.4), and page consolidation (§5.3 rewrites prose *from* the ledger). Claims are indexed into SQLite alongside pages. Trade-off, stated honestly: frontmatter gets heavier and hand-editing claims is fussier than prose — mitigate with `strata claim add|close|edit` CLI helpers and the linter validating ledger↔prose consistency.

### 6.5 Lifecycle jobs (scheduled, all idempotent, all git-committed)

1. **Decay sweep** — recompute confidence from half-lives; archive below threshold (already specced).
2. **Consolidation** — rewrite bloated pages from their ledgers (§5.3).
3. **Retention** — enforce `retain_days`; hard-delete per erasure mode.
4. **Lint** — orphans, broken `[[links]]`, unsourced claims, ledger/prose drift, injection-shaped content (§4.5).
5. **Eval** — scheduled `strata eval` runs, results committed to `evals/` so quality is itself git-tracked over time.

### 6.6 Review workflow ("memory PRs")

`review: auto | gated | off` in config. In `gated` mode the worker writes to `strata/staging`; auto-merge policy (min confidence, no contradictions, no injection flags, provenance ≥ threshold) merges the rest of the time; `strata review` presents pending diffs (rich TUI) for accept/edit/reject. Every decision is a commit — the audit story writes itself.

---

## 7. Project Structure (revised)

```
strata/
├── pyproject.toml                  # extras: [vector] [rerank] [pii] [rest] [ollama] [dev]
├── STRATA-FORMAT.md                # versioned portable-format spec (§4.2)
├── strata/
│   ├── __init__.py                 # exports Memory, AsyncMemory
│   ├── memory.py                   # mem0-shaped API (full parity table §5.1)
│   ├── config.py                   # pydantic-settings; env overrides; JSON Schema export
│   ├── schema.py                   # schema.md parsing (exists)
│   ├── models.py                   # pydantic: Page, Claim, PageOp, RawEntry, SearchHit
│   ├── storage/
│   │   ├── repo.py                 # page/raw IO, index.md, sharding
│   │   ├── git_backend.py          # pygit2 | dulwich | subprocess; batch commits; locks
│   │   └── erasure.py              # shard-per-user | filter-repo | crypto-shred (§4.1)
│   ├── write/
│   │   ├── pipeline.py             # queue, worker, batching, flush()
│   │   ├── extractors/             # anthropic.py · openai_compat.py · ollama.py · heuristic.py
│   │   ├── resolve.py              # contradiction detection, supersession, claim ledger ops
│   │   ├── pii.py                  # presidio gate (optional extra)
│   │   └── review.py               # staging branch, merge policy, review queue
│   ├── read/
│   │   ├── search.py               # tiered L0–L3, RRF, temporal/status filters
│   │   ├── fts.py                  # SQLite FTS5 (exists, extend w/ claims table)
│   │   ├── vectors.py              # Embedder + VectorStore plugins
│   │   ├── rerank.py               # rerankers-lib wrapper
│   │   └── pack.py                 # token-budgeted context packer (§5.6)
│   ├── lifecycle/
│   │   ├── decay.py · consolidate.py · retention.py · lint.py
│   │   └── scheduler.py            # APScheduler wiring
│   ├── interop/
│   │   ├── mem0_io.py · jsonl_io.py · memory_md.py     # import/export (§4.2)
│   ├── evals/
│   │   ├── harness.py              # strata eval; domain-eval generation from claim ledger
│   │   └── datasets/               # LoCoMo/LongMemEval/BEAM adapters (downloaded, not vendored)
│   ├── obs.py                      # logging, token accounting, optional OTel
│   ├── cli.py                      # + review, forget, eval, stats, doctor, import/export, claim
│   ├── mcp_server.py               # + wiki_supersede, wiki_history, wiki_review
│   ├── rest.py                     # FastAPI (optional extra)
│   └── templates/                  # schema.md, config.yaml
├── examples/                       # simple_chatbot.py · langchain · openai-sdk · fastapi app
├── tests/                          # unit + property tests (hypothesis) + golden-file compile tests
└── benchmarks/                     # latency @1K/10K/100K pages; published honestly
```

---

## 8. Tech Stack (all open source; core stays light)

| Layer | Default | Alternatives / notes |
|---|---|---|
| Language | Python ≥3.10 | unchanged |
| Truth storage | markdown + YAML frontmatter (`python-frontmatter`, `pyyaml`) in git | unchanged — the product |
| Git | **`pygit2`** (libgit2, fast, no subprocess) | `dulwich` (pure-py fallback), subprocess (last resort) |
| Index/FTS | stdlib `sqlite3` + FTS5, WAL mode | `tantivy-py` if FTS5 BM25 ever limits (Memvid's choice); not needed at target scale |
| Vectors (opt.) | **`sqlite-vec`** — brute-force, ~30MB RAM, fine to ~1M vectors, zero infra | `lancedb` for the >100K-pages tier (IVF-PQ, columnar); both embedded, no server |
| Embeddings (opt.) | **`model2vec`** static embeddings (~30MB, up to ~500× faster on CPU than transformers — retrieval in microseconds) | `fastembed` (ONNX, better quality, still light) → `sentence-transformers` → API (Voyage/OpenAI) — all behind `Embedder` |
| Reranker (opt.) | **`rerankers`** (AnswerDotAI unified API) + `gte-reranker-modernbert-base` (149M — benchmarks show it matches 1.2B models on Hit@1) | `mxbai-rerank-base-v2` (Apache-2.0), Qwen3-Reranker-0.6B; ONNX int8 for CPU |
| Fusion | RRF (in-house, ~10 lines, rank-only — no score calibration) | weighted fusion only if evals demand |
| Extraction LLM | `anthropic` SDK, **structured outputs via pydantic models** (Haiku 4.5 compile / Sonnet judgment — unchanged) | `instructor` or `litellm` for provider-agnostic structured extraction; **Ollama** for fully-offline (§5.8) |
| PII (opt.) | **`presidio-analyzer` / `presidio-anonymizer`** (MIT, active 2026 releases, purpose-built "before LLM context" use case) | regex-only fallback in core |
| Crypto (opt.) | `cryptography` (Fernet per-user keys), OS keyring via `keyring` | only for crypto-shred mode |
| Queue/jobs | stdlib `queue` + worker thread; **`APScheduler`** for sweeps | SQLite-backed queue table for crash-safe durability; no Redis/Celery ever required |
| Config | `pydantic` + `pydantic-settings` | JSON Schema export for editor support |
| CLI | `typer` + `rich` | unchanged |
| MCP | `mcp` / FastMCP | unchanged |
| REST (opt.) | FastAPI + uvicorn | Phase 2, mirrors Mem0 REST shape |
| Erasure | `git-filter-repo` (the maintained standard; never BFG/filter-branch) | §4.1 modes |
| Observability | `logging` + token ledger; opt. `opentelemetry-sdk` | `strata stats` |
| Graph (Phase 2) | SQLite recursive CTEs over a `links` table | `networkx` for algorithms; still no graph DB |
| Locks | `filelock` | — |
| Tests | `pytest` + `hypothesis` (property tests on parse/roundtrip) + golden compile fixtures | — |

**Install profile:** `pip install strata-memory` → pure-Python + pygit2 wheel, works immediately (heuristic extractor, FTS5 search). `strata-memory[local]` → model2vec + sqlite-vec + rerankers. `[pii]`, `[rest]`, `[ollama]` as needed. The core never imports torch.

---

## 9. Latency Engineering

Production context (2026 published figures): optimized managed-memory retrieval runs ~1.44s p95 vs ~17s for full-context stuffing; Supermemory's published budget for a 500ms retrieval window allocates ~120ms to vector search and ~100ms to reranking, reserving ~150ms for variance. Strata is embedded (no network hop), so beat these comfortably:

**Targets (commodity CPU, 10K pages):** `add()` enqueue ≤5ms p95 · L1 search ≤10ms p95 · L2 hybrid ≤50ms p95 (model2vec) / ≤150ms (fastembed) · L3 +80–150ms (149M ONNX-int8 reranker, top-20) · compile (async, off hot path) 1–3s/batch.

Techniques, in order of impact:

1. **Async write path** (§6.2) — turns the worst hot-path cost (LLM call) into background work.
2. **Tiered read** (§6.3) — L0 standing context answers the most common case with zero search; escalate only on need.
3. **Static embeddings by default** — model2vec makes query embedding a table lookup (microseconds); embedding cost stops mattering.
4. **Everything embedded** — SQLite WAL + sqlite-vec in-process; no network round trips anywhere in the read path.
5. **Incremental indexing** — update only changed pages on commit; full `reindex` reserved for recovery.
6. **Prompt-cache-friendly packing** — stable context ordering (§5.6) so the *downstream* LLM call gets prefix-cache hits; often worth more ms than any retrieval optimization.
7. **Query-result micro-cache** — `(query_hash, user_id, index_generation)` → results; invalidate on commit. Skip semantic caching (GPTCache-style) until evidence demands it.
8. **Batch compile** — N raw entries per LLM call with structured multi-doc output; cuts token cost ~30–50% and amortizes latency.
9. **Reranker off by default**, one flag on — measured, honest docs about the accuracy/latency trade.
10. **Publish `benchmarks/`** — p50/p95 at 1K/10K/100K pages, reproducible script. Incumbents self-report; being the framework with *reproducible* numbers is itself differentiation.

---

## 10. Accuracy Engineering

1. **Hybrid + rerank** (§6.3) — reproduces the retrieval stack of the current benchmark leaders (Hindsight's multi-strategy + cross-encoder pattern) with local models. In technical corpora, hybrid+rerank materially lifts MRR/P@1 over vector-only because BM25 recovers exact-token matches embeddings miss.
2. **Structured extraction with validation** (§5.7) — most "memory is wrong" failures are extraction failures; pydantic-validated output + retry + dead-letter beats prompt-and-pray.
3. **Contradiction resolution at write time** with model escalation (Haiku flags, Sonnet judges) — plus the review queue for low-confidence conflicts instead of silent guesses.
4. **Temporal correctness** — the claim ledger means superseded facts *cannot* surface as current (the exact failure LoCoMo's temporal category and Mem0's +29.6-point improvement target).
5. **Provenance-weighted retrieval** — rank user_stated above agent_inferred at equal relevance; trust ceilings (§4.5) stop confident-sounding garbage from imported/inferred claims.
6. **Consolidation** (§5.3) — clean pages retrieve better than append-scarred ones; this is an accuracy feature as much as hygiene.
7. **Index-summary routing** — the compiler seeing `index.md` (existing page ids/titles/tags) prevents duplicate-page sprawl, the classic wiki-memory failure mode. Add near-duplicate detection (embedding similarity ≥ threshold → propose merge in lint).
8. **Eval-driven development** (§11) — every retrieval knob (RRF k, rerank on/off, embedder choice) justified by a number from `strata eval`, not vibes.

---

## 11. Evaluation Plan (expanded from spec §14)

- **Public benchmarks:** LoCoMo + LongMemEval (comparability), **BEAM** (long-horizon degradation — be honest that everyone, including SOTA at 48.6–64.1, degrades), **HaluMem** (memory hallucination — pairs naturally with the provenance system). Report tokens/query and latency alongside accuracy, as the 2026 convention now demands.
- **Contradiction-recovery suite** (spec's idea — keep; the claim ledger makes it mechanically checkable).
- **Domain-eval generation** (§4.4): synthesize Q/A from your own repo's supersession history; ship as `strata eval --domain`.
- **Retrieval ablations:** L1 vs L2 vs L3 on every dataset → published table justifying the tiered defaults.
- **Poisoning red-team suite:** seed injection-shaped memories, verify lint/gating catches them; publish results (nobody else does).
- **Rule:** never quote incumbents' self-reported numbers as comparison baselines without reproduction — the category has a documented credibility problem here (spec §14 was right; keep it).

---

## 12. Revised Roadmap

**Phase 0 — done** (unchanged). Ship nothing new; dogfood.

**Phase 0.5 — Hardening (new, ~2–3 weeks, before any new features):**
async write pipeline + `flush()` (§6.2) · API parity: `update/delete/history/reset` (§5.1) · pygit2 backend, batch commits, filelock (§5.4) · pydantic models + structured extraction (§5.7) · context packer (§5.6) · `strata doctor` + stats/token ledger. *Exit criterion: the spec's original two-week dogfood, now on a write path that won't embarrass you in a real backend.*

**Phase 1 — Lifecycle + Trust (the differentiation phase):**
claim ledger + supersession + contradiction resolution (§6.4) · decay sweep + consolidation + retention (§6.5) · provenance typing + injection lint (§4.5) · review workflow / memory PRs (§6.6) · PII gate via presidio extra (§4.1) · erasure modes v1: shard-per-user + `strata forget` (§4.1) · import/export: Mem0 + JSONL + MEMORY.md (§4.2) · `STRATA-FORMAT.md` v1 · Ollama extractor (§5.8) · MCP additions (`wiki_supersede`, `wiki_history`, `wiki_review`).

**Phase 2 — Hybrid retrieval + Evals:**
Embedder/VectorStore/Reranker plugins with model2vec + sqlite-vec + rerankers defaults · RRF + tiered read path (§6.3) · `strata eval` harness incl. domain-eval generation + public-benchmark adapters (§11) · `benchmarks/` published · FastAPI REST layer · `git-filter-repo` + crypto-shred erasure modes · graph-lite (`[[wikilinks]]` → SQLite CTE traversal).

**Phase 3 — unchanged from spec** (multi-tenant/remote, only with demonstrated demand), plus: AsyncMemory promoted from wrapper to first-class; LanceDB backend for the >100K-page tier; alignment with whatever portable-memory standard has traction by then.

---

## 13. Risks, Shortcomings & Limitations (honest list — watch these)

1. **The window is closing.** Letta already proved git-native memory works; Mem0 already ships a local-first MCP server. A fast-follower with funding could ship "Mem0-API-over-files" in a quarter. Mitigation: speed on Phases 0.5–1, and moat via the compliance package, which requires sustained, unglamorous work funded players deprioritize.
2. **Git is the brand and the bottleneck.** History growth, many-small-files performance (worst on Windows/NTFS), lock contention under concurrency, and the history-vs-erasure tension (§4.1) are all real. There is a page-count ceiling (~10⁵/repo) beyond which this architecture is simply the wrong tool — document it rather than pretending otherwise.
3. **Eventual consistency of compiled memory** (§5.2) will surprise integrators expecting Mem0-style immediate searchability. Mitigate: raw-FTS stopgap + `flush()` + loud documentation. It's still a real behavioral difference from Mem0 — the compat story is "same shape," not "same semantics."
4. **LLM compile cost and routing errors persist** (spec §15 — still true). Batching (§9.8) and consolidation help cost; the review queue makes errors *visible*, which is the ceiling of what's achievable.
5. **Claim-ledger complexity tax.** §6.4 is the load-bearing upgrade and also the biggest hand-editability regression. If dogfooding shows humans fighting the frontmatter, simplify (page-level temporal fields only) before shipping — hand-editability is a core promise, not a nice-to-have.
6. **FTS5 is English-biased** (porter stemmer); model2vec quality trails full transformers, especially multilingual. Both are default-vs-upgrade documentation problems, but say so.
7. **Crypto-shred mode contradicts the greppability pitch** for the pages it covers. Position it as the regulated-deployment option, never the default; keep the tension explicit in docs.
8. **Benchmark credibility cuts both ways.** The category's numbers are self-reported and marketing-driven (this research encountered obvious content-marketing farms among the "comparison" sites). Publishing reproducible-but-modest numbers may *look* worse than competitors' inflated ones. Hold the line anyway — the target audience (regulated, burned-by-vendors) is precisely the audience that rewards verifiability.
9. **Demand risk remains unvalidated** (spec §15 — unchanged and still the biggest risk). The compliance wedge sharpens the hypothesis but doesn't prove it. The Phase 0.5 exit criterion (real dogfooding) and 3–5 design-partner conversations in regulated industries should precede Phase 2 investment.
10. **EU AI Act timing is an opportunity with a deadline attached:** full applicability August 2026 means the compliance story is most marketable *now*; slipping Phase 1 into 2027 forfeits the news cycle.

---

## 14. Open Decisions (input wanted, none blocking Phase 0.5)

1. **Erasure default:** shard-per-user layout as the default for any multi-user repo (recommended), or opt-in? Affects `Repo.init()` layout now.
2. **Claim ledger scope:** full bi-temporal ledger in Phase 1 (recommended §6.4), or page-level `valid_from/until` first and claims in Phase 2 (safer for hand-editability, weaker eval/temporal story)?
3. **Review default:** `auto` with lint-gating only (recommended — lower friction), or `gated` for user-scoped pages?
4. **REST layer priority:** Phase 2 as proposed, or earlier if a non-Python design partner appears?
5. **Name/trademark:** "Strata" remains a placeholder — PyPI (`strata-memory` appears free, `strata` is not), domain, and GitHub org checks still pending before anything public.

---

## Appendix A — Sources

**Competitors / market:**
[mem0ai/mem0 (GitHub)](https://github.com/mem0ai/mem0) · [Mem0 — State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026) · [Mem0 — AI Memory Benchmarks 2026: LoCoMo, LongMemEval & BEAM](https://mem0.ai/blog/ai-memory-benchmarks-in-2026) · [Mem0 pricing](https://mem0.ai/pricing) · [getzep/graphiti (GitHub)](https://github.com/getzep/graphiti) · [Zep: A Temporal Knowledge Graph Architecture for Agent Memory (arXiv 2501.13956)](https://arxiv.org/abs/2501.13956) · [Letta — Context Repositories](https://www.letta.com/blog/context-repositories/) · [Letta — Sleep-time Compute](https://www.letta.com/blog/sleep-time-compute/) · [Letta — Memory Blocks](https://www.letta.com/blog/memory-blocks/) · [rohitg00/agentmemory (GitHub)](https://github.com/rohitg00/agentmemory) · [LLM Wiki v2 (gist)](https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2) · [Graphlit — Survey of AI Agent Memory Frameworks](https://www.graphlit.com/blog/survey-of-ai-agent-memory-frameworks) · [vectorize.io — Best AI Agent Memory Systems](https://vectorize.io/articles/best-ai-agent-memory-systems) · [Atlan — Best AI Agent Memory Frameworks 2026](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/) · [EverMind — Open Source Agent Memory Frameworks 2026](https://evermind.ai/blogs/best-open-source-agent-memory-frameworks-2026)

**Gaps / governance / interop:**
[Atlan — AI Agent Memory Governance](https://atlan.com/know/ai-agent-memory-governance/) · [Atlan — Data Privacy for AI Agents](https://atlan.com/know/data-privacy-for-ai-agents/) · [VerityAI — AI Agent Memory: Privacy Compliance](https://verityai.co/blog/ai-agent-memory-privacy-compliance) · [Portable Agent Memory (arXiv 2605.11032)](https://arxiv.org/html/2605.11032v1) · [MemGuard (arXiv 2605.28009)](https://arxiv.org/pdf/2605.28009) · [MemTrust (arXiv 2601.07004)](https://arxiv.org/pdf/2601.07004) · [PROJECTMEM (arXiv 2606.12329)](https://arxiv.org/pdf/2606.12329) · [Cross-Tool Agent Memory & the Portability Problem](https://codex.danielvaughan.com/2026/04/17/cross-tool-agent-memory-mempalace-portability/) · [Conectia — MCP, Memory Limits, and the Interoperability Wall](https://conectia.pro/en/blog/ai-agents-mcp-interoperability-wall-2026)

**Tech stack:**
[asg017/sqlite-vec (GitHub)](https://github.com/asg017/sqlite-vec) · [lancedb/lancedb (GitHub)](https://github.com/lancedb/lancedb) · [MinishLab/model2vec (GitHub)](https://github.com/MinishLab/model2vec) · [qdrant/fastembed (GitHub)](https://github.com/qdrant/fastembed) · [HuggingFace — Static Embeddings (400× faster)](https://huggingface.co/blog/static-embeddings) · [AnswerDotAI/rerankers (GitHub)](https://github.com/AnswerDotAI/rerankers) · [AIMultiple — Reranker Benchmark](https://aimultiple.com/rerankers) · [Hybrid Search: BM25, Vector & Reranking Reference 2026](https://www.digitalapplied.com/blog/hybrid-search-bm25-vector-reranking-reference-2026) · [Supermemory — Memory Retrieval Latency Budgets (May 2026)](https://blog.supermemory.ai/latency-budgets-memory-retrieval/) · [microsoft/presidio (GitHub)](https://github.com/microsoft/presidio) · [Presidio docs](https://microsoft.github.io/presidio/)

*All star counts, prices, and benchmark figures are as reported at research time (2026-07-06); benchmark numbers are vendor-self-reported unless independently reproduced. Re-verify before quoting externally.*
