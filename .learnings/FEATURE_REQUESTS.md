# Feature Requests Log

User-requested capabilities and improvement ideas that emerged during development.

---

## [FEAT-20260609-001] self_improvement — cross-agent learning sharing

**Logged**: 2026-06-09T12:37:00+08:00
**Priority**: medium
**Status**: pending
**Area**: docs

### Requested Capability

Create a `.learnings/` directory in the project to share corrections, best practices, and error resolutions across different AI coding agents (Hermes Agent, Claude Code, Codex, etc.).

### User Context

The user wants learnings to persist beyond a single agent's memory system, so any tool used on this project benefits from past corrections.

### Complexity Estimate

simple

### Suggested Implementation

Already done for this session:
- Created `/home/ubuntu/lvb-digital-employee/.learnings/`
- Seeded LEARNINGS.md with 7 entries from past project experience
- Seeded ERRORS.md with 3 entries
- Created this FEATURE_REQUESTS.md

### Metadata

- Frequency: first_time
- Related Features: self-improvement skill

---

## [FEAT-20260515-001] product_render — single-flow upload reuse

**Logged**: 2026-05-15T10:00:00+08:00
**Priority**: high
**Status**: resolved
**Area**: frontend

### Requested Capability

In PicMagic product render mode, skip Step3 upload and reuse Step1 uploaded images automatically.

### User Context

Users consistently failed to re-upload images in Step3, resulting in text-to-image instead of product rendering. The user demanded a single-flow UX.

### Complexity Estimate

simple

### Suggested Implementation

Already implemented: auto-reuse Step1 image in render mode, no separate upload zone in Step3.

### Metadata

- Frequency: recurring (multiple user complaints until fixed)
- Related Features: picmagic render mode

---

## [FEAT-20260510-001] safety — backup branch before destructive git

**Logged**: 2026-05-10T09:00:00+08:00
**Priority**: critical
**Status**: resolved
**Area**: git

### Requested Capability

Before any destructive git operation (stash drop, reset --hard, force push), create a committed backup branch first.

### User Context

User lost work due to a destructive git operation. Now requires a safety net before any risky git command.

### Complexity Estimate

simple

### Suggested Implementation

Always: `git branch backup/YYYYMMDD-HHMM` before any `git reset --hard`, `git stash drop`, or `git push --force`.

### Metadata

- Frequency: first_time
- Tags: git, safety
