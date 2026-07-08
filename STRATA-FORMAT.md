# STRATA-FORMAT v1.0

The portable memory format (§4.2 of the architecture). A Strata memory repo is
human-readable without any software: markdown files with YAML frontmatter in a
git repository. This document is the versioned contract; the `format: "1.0"`
field in every page's frontmatter declares which revision it follows.
Semantic versioning: additive fields bump the minor version; breaking changes
bump the major.

## Repository layout

```
<repo>/
├── schema.md            # user-editable ontology (prose + one fenced yaml block)
├── config.yaml          # runtime knobs
├── index.md             # auto-generated, one line per page
├── wiki/                # compiled pages — THE memory
│   ├── g/<type>/<slug>.md               # shared/global pages
│   └── u/<user>/<type>/<slug>.md        # user-scoped pages
├── raw/                 # immutable, append-only sources
│   ├── g/<source_type>/<ts>__<origin>.md
│   ├── u/<user>/<source_type>/<ts>__<origin>.md
│   └── failed/          # dead-lettered extraction payloads
├── evals/               # committed eval results (optional)
└── .strata/             # DERIVED caches — never part of the format
```

**Erasure property:** all data about one user lives under exactly two path
prefixes (`wiki/u/<user>/`, `raw/u/<user>/`), so per-user deletion — including
history rewrite — is a path operation.

## Page ids

A page id is its path under `wiki/` without the `.md` extension, e.g.
`u/alice/user/profile` or `g/concept/aws-strategy`. The path is authoritative:
if a file is moved, its id changes with it. Each user has one canonical
profile page at `u/<user>/user/profile`.

## Page frontmatter

```yaml
---
type: user                  # one of the types declared in schema.md
id: u/alice/user/profile    # informational; the path is authoritative
title: alice
user_id: alice              # original (unslugged) user id; absent on global pages
agent_id: agent-1           # optional
run_id: run-9               # optional
tags: [seating, food]
created: '2026-07-06T08:14:00+00:00'    # ISO-8601, always UTC
updated: '2026-07-07T09:02:00+00:00'
confidence: 0.85            # base value at last update; readers apply decay
status: active              # active | superseded | archived
pinned: false               # pinned pages join standing context, never decay
sources: [raw/u/alice/conversation/2026-07-06T08-14-00__s1.md]
summary: One-line summary shown in index.md and packed context.
claims: [...]               # the claim ledger, see below
aliases: [anon-123]         # merged former user ids (user pages only)
metadata: {}                # integrator-defined
pii: [EMAIL]                # PII entity types detected at ingest (policy=tag)
format: '1.0'
---

Body: human-readable prose. Consolidation regenerates it from the ledger as
summary + "## Current" + "## History" + "## Notes".
```

## The claim ledger (bi-temporal)

Each claim is one provenanced fact with two timelines: **event time**
(`valid_from`/`valid_until` — when the fact was true in the world) and
**record time** (`recorded_at` — when the system learned it; `git log` gives
the full record-time history for free).

```yaml
claims:
  - id: c-2026-07-06-a3f1b2c4d5           # unique, stable
    text: "Prefers aisle seats"
    subject: preference:seat               # normalized key; same subject + new fact => supersession
    valid_from: '2026-07-06'
    valid_until: null                      # null = currently believed true
    recorded_at: '2026-07-06T09:02:00+00:00'
    confidence: 0.9                        # capped by the provenance trust ceiling
    provenance: user_stated                # user_stated | agent_inferred | tool_derived | imported | human_edited
    sources: [raw/u/alice/conversation/2026-07-06T08-14-00__s1.md]
    supersedes: c-2026-05-01-b2e0f1a2      # id of the claim this one replaced
```

Rules:

1. A claim is **active** iff `valid_until` is null.
2. Superseding closes the old claim's `valid_until` (= new claim's
   `valid_from`) and records `supersedes` on the new claim. Nothing is deleted.
3. "What was believed on date D" = claims with
   `valid_from <= D < valid_until-or-infinity`.
4. `confidence` may never exceed the trust ceiling for the claim's provenance
   (declared in `schema.md`; defaults: user_stated/human_edited 1.0,
   tool_derived 0.9, agent_inferred 0.8, imported 0.6).

## Raw entries

```yaml
---
source_type: conversation
origin: session-1
user_id: alice
created: '2026-07-06T08:14:00+00:00'
pii: [EMAIL]
---

verbatim ingested text (masked before persistence when pii.policy = mask)
```

Raw entries are immutable: nothing edits them after the fact.

## Interchange

- **JSONL** (lossless): one JSON object per page — all frontmatter fields plus
  `body`. First line is `{"strata_format": "1.0", "kind": "header"}`.
- **Mem0 JSON** (lossy): one record per active claim
  (`id/memory/user_id/created_at/updated_at/metadata`). Importing from Mem0
  produces `provenance: imported` claims, ceiling-capped.
- **MEMORY.md** (lossy): Claude Code auto-memory layout — an index file plus
  one markdown file per page.

## Derived caches (explicitly not format)

Everything in `.strata/` (FTS index, vector index, write queue, review queue,
ledgers, locks) is derived state. Deleting `.strata/` and running
`strata reindex` must reproduce identical search behavior from the markdown.
