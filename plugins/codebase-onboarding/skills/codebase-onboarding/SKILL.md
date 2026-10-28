---
name: codebase-onboarding
description: Generate an interactive onboarding atlas (a self-contained web UI) for any existing codebase — service map from frontend through auth, gateway, compute and data stores, end-to-end request flows, auth model, data model, API catalog, code map, setup/deploy steps, operations runbook, glossary and hotspots. Use this whenever someone is new to a project, inherits a legacy or unfamiliar repo, asks "how does this system fit together", "map the architecture", "document this codebase", "draw the service map", "where does auth happen", "trace a request end to end", or wants onboarding docs for a teammate — even if they don't say "onboarding". Stack-agnostic — works for AWS, Azure, GCP, containers, monoliths and monorepos in any language.
---

# Codebase Onboarding Atlas

Produce `atlas.json` (a stack-neutral description of the system) and `atlas.html` (a single-file web UI that renders it) for a repository. The goal is a new developer understanding the system in an hour instead of a month.

Three principles drive everything below:

1. **Facts first, inference labelled.** Every node and edge carries `confidence: "declared"` (found in config/IaC/code) or `"inferred"` (your reasoned guess). New devs trust the map only if it never pretends. Unknowns go into `gaps` as questions — an honest "who owns billing?" beats an invented answer.
2. **Scanner drafts, you enrich.** `scripts/scan.py` cheaply finds what config files declare. It can't understand intent, so you read the code to add flows, auth, data access patterns, glossary and the tour.
3. **Map by reading, not by running.** This is a documentation task. The user is waiting, and every minute spent building environments is a minute not spent understanding the system. Read code; don't execute the project.

## Budget: read, don't run, write only what you add

The only commands this skill runs are its own scripts (`scan.py`, `merge.py`, `render.py`), `git` read commands, and file reads/greps. Unless the user explicitly asks for verification ("check the setup works", "deep mode", "run the tests"):

- **Never execute the project — not even once "just to check".** No dependency installs, virtualenvs, test runs, builds, migrations, linters, containers, `python -c "import …"` probes or deploy/CLI tools. A newcomer reading "Run the tests: `pytest`" is served fine by a step taken from the repo; proving it costs minutes and tells them little. Leave `verified` unset — the viewer labels the steps "taken from repo files, not run".
- **Spot blockers by reading.** If a pin looks incompatible with current runtimes (e.g. an old library on a new Python), record it as a `runbooks` entry or `gaps` question, phrased as likely rather than confirmed.
- **Read selectively.** Small repo (roughly under 40 code files): reading most of it is fine. Larger: read IaC/config, entry points and the handlers on the key flows; grep for the rest (`grep -rn "TABLE_NAME\|QUEUE_URL"` beats opening 50 files). Never re-read a file.
- **Load references by section.** `references/schema.md` and `references/enrichment.md` have contents lists — read only the sections you need, and only the enrichment section for the detected stack.
- **Write only what you add.** Generating text is the slowest, most expensive part of this skill. Never rewrite or re-emit the scanner's output (config keys, pipeline, entry points, scanned nodes). Write a patch with just your additions and corrections, and let `merge.py` combine them (step 3).
- **Keep it tight.** Notes and descriptions: one sentence. Flows: 3–5, each ≤ 8 steps. Tour: 5–7 stops. Runbooks ≤ 6, hotspots ≤ 8, glossary ≤ 12. A new dev skims; extra prose costs time without adding understanding.

A small repo should finish in a few minutes. If you notice yourself on a side quest, stop and return to the map.

**Deep mode (opt-in only).** When the user asks for it, you may run the setup steps in a scratch/temp location (never inside the repo), cap it at two attempts per step, and set `"verified": true` on steps that worked. Report failures as runbook entries rather than fixing the project.

## Where files go

The atlas is a deliverable the user opens, edits and commits, so it belongs in their repo, not in a temp or scratchpad folder they will never find:

- **Deliverables:** `<repo-root>/docs/onboarding/atlas.json` and `<repo-root>/docs/onboarding/atlas.html`, where `<repo-root>` is the directory the user started the session in. Use another folder only if the user names one, or if `docs/onboarding/` already holds unrelated files (then use `docs/onboarding-atlas/`).
- **Working files only** (throwaway scans for diffing; deep-mode environments) go in a scratch/temp location, so the repo stays clean apart from the two deliverables.

Run the scripts with whatever Python the machine has: `python3` on macOS/Linux; on Windows try `py` first, then `python` (`python3` there is often a Microsoft Store stub).

## Workflow

### 0. Check for an existing atlas

If `<repo-root>/docs/onboarding/atlas.json` exists, go to **Updating an existing atlas** below instead of starting over.

### 1. Scan

```bash
python3 <skill-dir>/scripts/scan.py <repo-root>
```

With no `-o`, it writes `<repo-root>/docs/onboarding/atlas.json`. It refuses to overwrite an atlas that already has human enrichment (summary, flows, tour); pass `-o` to a temp path when diffing.

Stdlib only (uses PyYAML if present). It detects frameworks, auth SDKs, cloud SDK clients, Serverless/SAM/CloudFormation, Terraform, CDK hints, docker-compose, Kubernetes, OpenAPI, Prisma, env var names (never values), CI pipelines, CODEOWNERS, ADRs, and git churn hotspots. Its stderr summary lists every node id and edge, which is all you need to write a patch — don't read the scanned JSON in full. Note what it found nothing for.

### 2. Orient

Read, in order: README, the scan output, IaC/config files, then entry points and the handlers on the main paths. Form a one-paragraph mental model before writing JSON. Ask the user only for things the repo cannot tell you (environment URLs, owners, tribal knowledge) — and record unanswered ones in `gaps` instead of blocking.

### 3. Enrich with a patch

Write your additions to a patch file in a scratch/temp location, then merge it into the scanned atlas:

```bash
python3 <skill-dir>/scripts/merge.py <repo-root>/docs/onboarding/atlas.json <scratch>/patch.json
```

Patch rules (also in the script's docstring):
- `nodes` upsert by `id` — send only new nodes or the fields you're changing (e.g. `{"id": "orders-fn", "notes": "…"}`).
- `edges` upsert by `from`+`to`+`kind`.
- `remove_nodes: ["id", …]` and `remove_edges: [{"from","to","kind"}, …]` delete scanner mistakes.
- Objects (`meta`, `auth`, `data`, `run`, `operate`, `context`, `code`) merge key by key.
- Other lists (`flows`, `apis`, `tour`, `gaps`, `run.setup`, …) replace the existing list; prefix the key with `+` to append instead (`"+gaps": ["…"]`).

Write the patch in one go. If render later reports an error, send a second tiny patch rather than rewriting.

Work through the layers; skip any that genuinely don't apply rather than padding them. Field shapes are in `references/schema.md` (read just the sections you're filling).

| Layer | What to add | Where the truth usually lives |
|---|---|---|
| Map | Missing nodes/edges, especially compute→data and service→service calls | SDK client calls, env vars naming tables/queues/URLs, IAM policies |
| Flows | 3–6 key user journeys as ordered steps (login, core read, core write, async job) | Route handlers, middleware, queue consumers |
| Auth | Provider, token type, where verified, roles/scopes and what they unlock | Authorizers, middleware, guards, IAM |
| Data | Entities, keys, access patterns, owning service | Schemas, ORM models, table definitions, query code |
| APIs | Method, path, handler, auth requirement | Gateway config, routers, OpenAPI |
| Code | Entry points and modules with one-line purposes | Folder structure, imports |
| Run & Ship | Setup steps as the repo declares them, environments, config keys, pipeline stages | package scripts, Makefile, CI files, `.env.example`, README |
| Operate | Where logs/metrics live, alarms, symptom→check→fix runbooks | Logger setup, monitoring IaC, incident docs |
| Context | Glossary of domain terms, owners, decisions, hotspots | Code names, CODEOWNERS, ADRs, git history |
| Tour | 5–8 ordered stops that teach the system, each pointing at nodes/files | Your synthesis |

Bugs or risks you spot while reading are valuable — put them in `context.hotspots` with a one-line reason. Don't fix them; this skill documents.

Write node IDs as stable kebab-case (`api-gateway`, `orders-lambda`, `orders-table`). Keep labels short; put detail in `notes`. Every edge should say what crosses it (`label`: "JWT", "PutItem", "orders.created event").

### 4. Render and check

```bash
python3 <skill-dir>/scripts/render.py <repo-root>/docs/onboarding/atlas.json
```

It writes `atlas.html` next to the JSON. `render.py` validates first (dangling edge endpoints, flow steps naming unknown nodes, missing required fields) and prints warnings — fix errors with small edits and re-render. Warnings about optional sections are fine to leave. Don't open a browser or take screenshots unless one is already set up; the validator is enough.

### 5. Deliver

Tell the user both files are in `docs/onboarding/` in their repo, and give the full path to `atlas.html` plus the command to open it (`start <path>` on Windows, `open <path>` on macOS, `xdg-open <path>` on Linux). `atlas.json` is the source — they can commit it, diff it, regenerate. Summarise in a few lines: what the system is, the biggest gaps found, and the first place a new dev should look. Mention that setup steps were taken from repo files and not run, and that they can ask for deep mode to verify them.

## Quality bar

- A newcomer can answer from the atlas alone: How does a user log in? What happens when they click the main action? Where is the data? How do I run it locally? Where do I look when it breaks?
- No secrets. Record env var **names** and where they're set, never values — scan.py already skips real `.env` values; keep it that way when enriching.
- Prefer fewer, correct nodes over exhaustive noise. Group 40 near-identical Lambdas into one node with `notes` listing them, unless they differ in what they touch.
- When the project is huge, map one bounded slice well (e.g. the checkout path) and list the rest in `gaps` rather than skimming everything.

## Updating an existing atlas

If `docs/onboarding/atlas.json` already exists:

1. Scan to a temp file (`-o <scratch>/atlas.new.json`) and compare node/edge sets with the existing atlas — don't re-read the whole codebase.
2. **Nothing changed:** re-render (so the HTML picks up any viewer updates), then reply briefly with the full path to `atlas.html` and the open command. Don't repeat the whole summary unless asked.
3. **Something changed:** read only the changed areas and write a patch for `merge.py` — new declared items as upserts, removed ones as `"+gaps": ["<id> no longer detected — removed or renamed?"]` — then re-render. Human-written enrichment (flows, notes, glossary, tour) stays because the patch only touches what you name.
