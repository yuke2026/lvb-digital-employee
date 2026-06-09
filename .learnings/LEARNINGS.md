# Learnings Log

Corrections, best practices, and knowledge gaps discovered during development.

---

## [LRN-20260609-001] correction — aggressive proactive saving

**Logged**: 2026-06-09T12:34:00+08:00
**Priority**: high
**Status**: resolved
**Area**: config

### Summary

User wants me to save important decisions/conclusions to Memory and complex workflows as Skills more aggressively and proactively, without waiting to be asked.

### Details

- Every important decision → Memory immediately
- Every complex task (5+ tool calls) completed → offer to save as Skill
- Every Skill used and found incomplete → patch before session ends
- Err on side of more, not less

### Suggested Action

Already applied — Memory entries updated and 5-question criteria saved.

### Metadata

- Source: user_feedback
- Related Files: ~/.hermes/skills/software-development/digital-employee/SKILL.md
- Tags: behavior, memory, skills

---

## [LRN-20260609-002] best_practice — memory saving criteria

**Logged**: 2026-06-09T12:35:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: config

### Summary

5-question framework to decide whether something should be saved to Memory.

### Details

Ask these 5 questions:
1. Will this decision affect future development?
2. If I forget, will the user have to repeat themselves?
3. Did the user explicitly reject a方案/approach?
4. Is this an architecture or technology selection rationale?
5. What does the user need to know to seamlessly continue next time?

If ANY answer is "yes", save it.

### Metadata

- Source: conversation
- Tags: memory, criteria, decision

---

## [LRN-20260609-003] best_practice — context loss recovery

**Logged**: 2026-06-09T12:36:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: docs

### Summary

When session context is lost (e.g., long gap between conversations), use session_search to find the last session and tell the user what's changed since then.

### Details

Useful approach: 
1. Check recent sessions with session_search(query="")
2. Check git log for recent commits
3. Check project status (service, DB, files)
4. Present a clean summary and ask what to do next

### Metadata

- Source: experience
- Tags: process, context, recovery

---

## [LRN-20260520-001] correction — Feishu embedded browser does not support confirm()

**Logged**: 2026-05-20T14:00:00+08:00
**Priority**: critical
**Status**: resolved
**Area**: frontend

### Summary

All delete/restore/push confirmations must use custom modals, not `confirm()`/`alert()`/`prompt()`.

### Details

Feishu's embedded browser does not support JavaScript `confirm()`, `alert()`, or `prompt()`. These calls silently hang and the user cannot proceed.

Fix: Every data-modifying action must use a custom modal with:
- `fixed inset-0 z-[60]` positioning
- Gradient icon area (danger=red, safe=green)
- Title + description + cancel/confirm buttons
- Separate state variables for each modal

Already applied in the codebase (报告三改 commits 980be12 + 39558d0).

### Metadata

- Source: user_feedback
- Related Files: frontend/index.html
- Tags: feishu, modal, confirmation, pitfall

---

## [LRN-20260515-001] best_practice — PicMagic rendering: no separate upload area

**Logged**: 2026-05-15T10:00:00+08:00
**Priority**: high
**Status**: resolved
**Area**: frontend

### Summary

In render mode, reuse Step1 images automatically — do not create a separate upload zone.

### Details

Users don't realize they need to upload again in Step3, resulting in "no reference image" text-to-image instead of product rendering. Always auto-reuse Step1 images.

### Metadata

- Source: user_feedback
- Related Files: /home/ubuntu/bg-eraser/frontend/index.html
- Tags: ux, picmagic, render

---

## [LRN-20260515-002] correction — WenQuanYi Zen Hei needed for PDF Chinese text

**Logged**: 2026-05-15T10:30:00+08:00
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary

fpdf2 requires WenQuanYi Zen Hei font for Chinese character support in PDFs.

### Details

- Font path: `/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc`
- Do NOT use DejaVu Sans (no CJK glyphs)
- WenQuanYi Zen Hei also lacks emoji — use plain text labels (`[优势]` instead of `💪`)

### Metadata

- Source: user_feedback
- Related Files: backend/app/api/v1/report_pdf.py
- Tags: pdf, chinese, font, pitfall

---

## [LRN-20260510-001] knowledge_gap — Tencent Cloud GitHub access

**Logged**: 2026-05-10T09:00:00+08:00
**Priority**: high
**Status**: resolved
**Area**: infra

### Summary

Tencent Cloud server cannot reach GitHub via HTTPS (git push times out). Must use SSH on port 443.

### Details

```bash
git config --global core.sshCommand "ssh -p 443 -o StrictHostKeyChecking=no"
git remote set-url origin git@ssh.github.com:owner/repo.git
```

Also: ghproxy.net proxies downloads but NOT git push.

### Metadata

- Source: error
- Tags: github, network, tencent-cloud, ssh

---

## [LRN-20260510-002] correction — never destructive git without backup branch

**Logged**: 2026-05-10T09:05:00+08:00
**Priority**: critical
**Status**: resolved
**Area**: git

### Summary

Before any destructive git operation (stash drop, reset --hard, force push), MUST create a committed backup branch first.

### Details

This is a hard requirement from the user. Never skip this step.

### Metadata

- Source: user_feedback
- Tags: git, safety
