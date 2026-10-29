# Changelog

# 0.8.0 — 2026-10-29
Vercel-style viewer: top tab navigation, centered layout, project header.
Geist and Geist Mono embedded in every atlas, so it renders correctly offline.
Packaged as a Claude Code plugin marketplace (/plugin marketplace add Shuashuaa/codebase-onboarding).

# 0.7.0 — 2026-10-29
merge.py: enrichment is written as a small patch and merged, instead of rewriting the scanned atlas.
Scanner prints every node id and edge, so the agent doesn't need to read the scanned JSON.
Size limits on notes, flows, tour, runbooks, hotspots and glossary.

# 0.6.0 — 2026-10-29
Read-only by default: no dependency installs, virtualenvs, tests or builds. Optional "deep mode" verifies setup steps.
Scanner refuses to overwrite an enriched atlas without --force.
Setup steps are labelled as taken from repo files unless verified.

# 0.5.0 — 2026-10-29
Minimal monochrome viewer with Geist type and light/dark themes.

# 0.4.0 — 2026-10-29
Experimental pastel theme (replaced in 0.5.0).

# 0.3.0 — 2026-10-29
Atlas is written to docs/onboarding/ in the mapped repo instead of a temp folder.
Windows fixes: ASCII console output, py/python guidance.
Map layout changed to top-to-bottom layers that wrap.
# 0.2.0 — 2026-10-28
render.py: validator and single-file HTML renderer.
Viewer with service map, flows, APIs, auth, data, code, run & ship, operate and context tabs.
Skill workflow (SKILL.md): scan, orient, enrich, render, deliver.
# 0.1.0 — 2026-10-28
scan.py: stack-agnostic scanner for frameworks, auth SDKs, cloud SDKs, Serverless/SAM/CloudFormation, Terraform, CDK, Compose, Kubernetes, OpenAPI, Prisma, env var names, CI, CODEOWNERS, ADRs and git hotspots.
Atlas schema and stack-specific enrichment guide.