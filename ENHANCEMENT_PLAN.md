# EEU Internal Audit Management System — Enhancement Plan (SUPERSEDED)

> **Do not act on this document.** It was written on **2026-07-31** against a codebase that no longer
> exists, and it is kept only as a historical marker. Its body has been removed rather than left in
> place, because a reader who skimmed it would have been actively misled.
>
> The original is still in git if you need it:
>
> ```bash
> git show HEAD:ENHANCEMENT_PLAN.md
> ```

## Why it is superseded

The plan was a ranked list of gaps — no server-side role enforcement, no time-based automation, no
shared frontend context or component library, unguarded routes, a disconnected risk pipeline, a
hardcoded dashboard. **Nearly all of it has since been implemented**, which is precisely what makes
the document dangerous to keep: it describes the system as it was before the RBAC layer, the
`AuthContext`/toast/UI-primitive layer, the API modules, the notification emitters, the audit-domain
state machines, the asynchronous report generation and the dashboard wiring.

Two of its own findings were also **wrong**, and are worth knowing about for anyone reading the git
copy:

- **2.7** claimed `changes` and `user_agent` were always empty and that three apps had no audit-trail
  coverage. Measured, both are false — `log_audit` fills them and every app logs.
- **2D** assumed `AuditTrail` needed a backfill. It did not; the real gap was downstream, in the
  frontend, which rendered no column for the diff it was already being sent.

## What was genuinely outstanding

Of the whole document, only **one** item was still real: **5.5, "Extend i18n to page content"** — the
chrome is translated but page bodies are hardcoded English. That work is carried forward, and the
rest of the document is closed.

For the current state of the system, the authoritative sources are the code, [TESTING.md](TESTING.md)
(the test map and role-by-role walkthrough) and [USER_MANUAL.md](USER_MANUAL.md).
