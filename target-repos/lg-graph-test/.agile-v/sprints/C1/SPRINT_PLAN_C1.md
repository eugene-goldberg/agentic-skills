# Sprint Plan: Cycle C1 Sprint 1

## Goal
Establish the secure multi-tenant foundation for Project Tracker v1 by delivering authentication, private workspaces, membership controls, project creation/listing, and task creation with privacy-preserving authorization for REQ-0001 through REQ-0009 plus REQ-0017/0018 coverage in the first vertical slices.

## Committed
| BL-ID | Story | REQ | Priority | Est | Status |
|---|---|---|---|---|---|
| BL-0001 | Authentication foundation and current-user access | REQ-0001, REQ-0002 | CRITICAL | 5 | Todo |
| BL-0002 | Workspace creation and my-workspaces listing | REQ-0003, REQ-0006 | CRITICAL | 5 | Todo |
| BL-0003 | Workspace membership add with privacy-preserving authorization | REQ-0004, REQ-0017 | CRITICAL | 3 | Todo |
| BL-0005 | Project creation inside a private workspace | REQ-0007, REQ-0017, REQ-0018 | CRITICAL | 3 | Todo |
| BL-0006 | Project listing within workspace | REQ-0008, REQ-0017 | HIGH | 2 | Todo |
| BL-0007 | Task creation with workspace-scoped assignee validation | REQ-0009, REQ-0017, REQ-0018 | CRITICAL | 5 | Todo |
**Total Committed:** 23 points

## Stretch (if capacity)
| BL-ID | Story | REQ | Priority | Est |
|---|---|---|---|---|
| BL-0012 | My assigned tasks endpoint | REQ-0016, REQ-0017 | HIGH | 3 |
**Total Stretch:** 3 points

## Capacity
**Velocity (last 3):** n/a, n/a, n/a → Avg: n/a for new team/project · **Team:** Assumed 2 engineers · **Duration:** 10 working days · **Absences:** none known
**Available:** 20-23 points (conservative startup range) | 26 points (optimistic)

## Risks
| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| 404 vs 403 privacy semantics implemented inconsistently across routers | Medium | High | Add explicit acceptance checks per BL and review auth helper usage before coding | Eng Lead |
| Assignee validation may accidentally leak user existence across tenants | Medium | High | Treat non-member assignee cases as 404 and test with outsider users early | Eng + QA |
| New repo has no visible app scaffold beyond virtualenv | High | Medium | Start with minimal FastAPI project skeleton aligned to engineering guide before feature slices | Eng |
| Referential integrity for future member removal/comment cleanup may be under-modeled if task/project relations are rushed | Medium | Medium | Define ORM relationships and deletion strategy during first data-model pass | Eng |

## Definition of Done
[ ] All acceptance criteria pass (from REQ Verification) · [ ] Unit tests pass · [ ] Code reviewed + merged · [ ] REQ Done Criteria complete · [ ] Regression passes · [ ] Docs updated (if user-facing)

## Handoff to Pipeline
**Committed REQs:** REQ-0001, REQ-0002, REQ-0003, REQ-0004, REQ-0006, REQ-0007, REQ-0008, REQ-0009, REQ-0017, REQ-0018
**Cycle Scope:** Sprint 1 covers the platform foundation and first secure collaboration slices for Cycle C1.
**Compliance:** Sprint contributes traceable evidence for private-workspace authorization, tenant isolation, and initial data integrity behavior.
