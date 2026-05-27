# Sprint Plan: Cycle 1 Sprint 1

## Goal
Deliver the foundational auth layer, workspace management, and project/task core for Project Tracker v1, with strict cross-tenant privacy and role enforcement.

## Committed
| BL-ID | Story | REQ | Priority | Est | Status |
|---|---|---|---|---|---|
| BL-0001 | Project Bootstrap and Database Schema | REQ-0022 | CRITICAL | 5 | Todo |
| BL-0002 | Authentication Signup and Login | REQ-0001, REQ-0002, REQ-0022 | CRITICAL | 5 | Todo |
| BL-0003 | Current User Endpoint | REQ-0003, REQ-0022 | CRITICAL | 2 | Todo |
| BL-0004 | Workspace Creation | REQ-0004, REQ-0022 | CRITICAL | 3 | Todo |
| BL-0005 | Workspace Listing and Detail | REQ-0008, REQ-0020, REQ-0022 | CRITICAL | 3 | Todo |
| BL-0006 | Workspace Membership Management | REQ-0005, REQ-0021, REQ-0020, REQ-0022 | CRITICAL | 4 | Todo |
| BL-0008 | Workspace Deletion Cascade | REQ-0009, REQ-0021, REQ-0020, REQ-0022 | HIGH | 3 | Todo |
| BL-0009 | Project Creation | REQ-0010, REQ-0021, REQ-0020, REQ-0022 | HIGH | 3 | Todo |
| BL-0010 | Project Listing | REQ-0011, REQ-0020, REQ-0022 | HIGH | 2 | Todo |
| BL-0011 | Project Update and Delete | REQ-0012, REQ-0021, REQ-0020, REQ-0022 | HIGH | 3 | Todo |
| BL-0012 | Task Creation with Assignment | REQ-0013, REQ-0014, REQ-0021, REQ-0020, REQ-0022 | HIGH | 4 | Todo |
| BL-0013 | Task Listing | REQ-0015, REQ-0020, REQ-0022 | HIGH | 2 | Todo |
| BL-0014 | Task Update and Delete | REQ-0016, REQ-0021, REQ-0020, REQ-0022 | HIGH | 3 | Todo |
| BL-0015 | Comments on Tasks | REQ-0017, REQ-0020, REQ-0022 | MEDIUM | 3 | Todo |
| BL-0016 | My Assigned Tasks Endpoint | REQ-0018, REQ-0020, REQ-0022 | MEDIUM | 3 | Todo |
| BL-0017 | Workspace Summary Endpoint | REQ-0019, REQ-0020, REQ-0022 | MEDIUM | 3 | Todo |

**Total Committed:** 51 points

## Stretch (if capacity)
| BL-ID | Story | REQ | Priority | Est |
|---|---|---|---|---|
| BL-0007 | Workspace Member Removal with Assignee Clearing | REQ-0006, REQ-0007 | HIGH | 4 |

**Total Stretch:** 4 points

## Capacity
**Velocity (last 3):** N/A (new project) → Avg: N/A · **Team:** 2 engineers · **Duration:** 10 days · **Absences:** None assumed
**Available:** 51 points (conservative estimate for 2 engineers over 10 days with learning curve)

## Risks
| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| Privacy semantics (404 vs 403) are easy to mix up | High | High | Explicit acceptance criteria on every BL; dedicated test story (BL-0018) | PO |
| Assignee-clearing on member removal is a cross-table transaction | Medium | Medium | Defer to stretch (BL-0007) until task layer is solid | PO |
| Bearer token implementation choice affects all protected routes | Medium | High | Spike in BL-0002 first; use dependency-injection pattern | Eng |

## Definition of Done
- [ ] All acceptance criteria pass (from REQ Verification)
- [ ] Unit tests pass
- [ ] Code reviewed + merged
- [ ] REQ Done Criteria complete
- [ ] Regression passes
- [ ] Privacy semantics (404 for non-members, 403 for wrong-role members) verified on every affected endpoint

## Handoff to Pipeline
**Committed REQs:** REQ-0001, REQ-0002, REQ-0003, REQ-0004, REQ-0005, REQ-0008, REQ-0009, REQ-0010, REQ-0011, REQ-0012, REQ-0013, REQ-0014, REQ-0015, REQ-0016, REQ-0017, REQ-0018, REQ-0019, REQ-0020, REQ-0021, REQ-0022
**Cycle Scope:** Sprint 1 covers ~95% of Cycle 1 (remaining: BL-0007 member removal, BL-0018 privacy test suite)
**Compliance:** Sprint contributes to Cycle 1 Validation Summary (Gate 2)
