# Project memory

A running log of what's been built in CareerOps, phase by phase, and the
reasoning behind the non-obvious decisions — for whoever (human or AI)
picks this project back up without the original conversation history.

See [CLAUDE.md](../CLAUDE.md) for the architecture reference and the hard
rules that constrain every phase. This folder is the "how we got here and
what's left" companion to that — read [known-gaps.md](known-gaps.md) first
if you're about to assume the pipeline runs end-to-end; it doesn't yet.

- [phase-0-1-scaffold.md](phase-0-1-scaffold.md) — pre-existing: hard filters, job scorer, DB schema
- [phase-2-document-generation.md](phase-2-document-generation.md) — resume + cover letter generation
- [phase-3-validators.md](phase-3-validators.md) — claim + ATS validation
- [phase-4-dashboard.md](phase-4-dashboard.md) — Streamlit review dashboard
- [phase-5-ingestion.md](phase-5-ingestion.md) — Greenhouse + Lever job ingestion
- [phase-6-tracker.md](phase-6-tracker.md) — manual-submit tracking
- [known-gaps.md](known-gaps.md) — what's NOT done yet
