---
name: github-pr
description: >-
  Opens and manages GitHub pull requests for vic_fuel_info: branch hygiene, CI,
  merge-ready checks, and Streamlit/Supabase deploy notes. Use when the user
  asks for a PR, merge prep, GitHub Actions review, or to hand work to a fresh
  agent session.
---

# GitHub PR & handoff (vic_fuel_info)

## When to use

- User wants a **PR** opened, updated, or reviewed.
- User wants **CI / Actions** (e.g. `ingest.yml`) verified after a change.
- User wants to **continue in a new Agent chat** with the same job (handoff).
- User reports **ingest day stuck on Fuel Up** but **Data Analysis date seems newer** → also load **`.cursor/skills/vic-fuel-ingest-ui/SKILL.md`** (`vic-fuel-ingest-ui`) and follow its evidence-first steps.

## PR checklist (this repo)

1. **Branch**: feature branch from `main`; small, focused diffs (project rules).
2. **CI**: `.github/workflows/ingest.yml` — DB + `SERVO_SAVER_API_CONSUMER_ID` secrets; non-zero exit on ingest failure (see `src/ingestion/run_ingest.py`).
3. **Deploy**: Streamlit Cloud — `src/app.py`, secrets mirror `.env.example`; DB migrations in `docs/migrations/` applied on Supabase when schema changes.
4. **Docs**: Prefer not adding new `.md` unless the user asked; update existing `README.md` / `docs/deployment.md` when behaviour changes.

## Hand off to another agent (you cannot be assigned remotely)

Cursor does not support queueing work to another agent from this chat. Do this instead:

1. **Open a new Agent (or Composer) chat** in the same repo.
2. **Attach this skill**: mention `@github-pr` or add **Project rules / Skills** so `github-pr` is included (path: `.cursor/skills/github-pr/SKILL.md`).
3. **Paste a short brief** (copy template below), filled in by the user or by the prior agent.

### Handoff template (paste into the new chat)

```text
Context: vic_fuel_info — use skill github-pr (.cursor/skills/github-pr).

Goal: [one sentence]

Done so far: [bullets]

Repo state: branch [name], commit [sha if known]

Blockers / questions: [or "none"]

What I need next: [e.g. open PR, fix failing workflow, verify ingest logs]
```

## Optional personal skill

For long **CI / merge babysitting** loops, the user may enable the personal skill **babysit** (`~/.cursor/skills-cursor/babysit/SKILL.md`) in that session in addition to this skill.

## Constraints

- Do not log or paste secrets (DB URL, API keys, consumer IDs).
- Match existing code style; avoid drive-by refactors.
