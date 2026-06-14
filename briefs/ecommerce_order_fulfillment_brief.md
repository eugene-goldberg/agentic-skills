# Brief — Order Fulfillment Lifecycle & Management

Target: `fullstack-ecommerce-app` (C#/.NET 8 + EF Core + Postgres + React/TS), branch `integration`.

## One-liner
Turn the dormant `OrderStatus` enum into a real order fulfillment lifecycle: orders move through an enforced state machine (Pending → Processing → Completed, plus Canceled), an **admin** advances an order's status, and a **customer** sees a live status tracker and can **cancel** their own order while it is still Pending — with full role-based authorization.

## Context
Build on the existing Order aggregate, `OrderStatus` enum, `OrderManagement` service, `UserRole`/JWT auth, and the existing Orders/Admin pages — mirror the existing aggregate + service + controller + xUnit/Moq patterns and the existing React pages/axios services. Do **NOT** modify the cart/pricing/checkout math, the generic AppController/BaseService machinery, the DbContext base wiring, or auth beyond reading the caller's role/identity.

## A. Status state machine (backend)
1. Allowed transitions are exactly: Pending→Processing, Processing→Completed, Pending→Canceled, and Processing→Canceled. Any other transition (e.g. Completed→anything, Canceled→anything, Pending→Completed) is rejected with a client error and no state change.
2. Each status change is recorded with its timestamp so the order exposes its current status and the time it entered that status (the data the customer timeline + admin view read).

## B. Admin advances status (backend + authz)
3. An **Admin** can advance an order to the next legal status via the API; the change persists and is reflected on a subsequent read.
4. A **non-admin** (regular user) attempting to advance any order's status is rejected with an authorization error (403) and no state change.

## C. Customer cancels own order (backend + authz)
5. The **owner** of an order can cancel it **only while it is Pending**; the order becomes Canceled and no further transitions are allowed. Cancelling a Processing/Completed order, or an already-Canceled order, is rejected with a client error and no state change.
6. A user attempting to cancel an order that is **not theirs** is rejected with an authorization error (403) and no state change.

## D. Customer status tracker UI (distinct, verifiable)
7. On the customer's Orders/order-detail view, each order shows a **status tracker** reflecting its current `OrderStatus` (the Pending→Processing→Completed progression visibly indicates where the order is; Canceled is shown distinctly), sourced from the server status (A.2).
8. A **Cancel order** control appears **only** when the order is Pending and the viewer is the owner; using it cancels the order and the view reflects Canceled without a full reload.

## E. Admin order-management UI (distinct, verifiable)
9. An Admin-only order-management view lists orders with their current status and provides an **Advance status** control that moves an order to its next legal status and reflects the new status in the view; the control is absent/disabled for terminal states (Completed/Canceled).
10. The admin view and its advance control are **not reachable/usable by a non-admin** user.

## F. Preservation (non-negotiable)
Every existing feature — products, cart, orders creation, payments, users, auth, wishlist, reviews, inventory — behaves exactly as today; all existing tests pass; existing endpoints/response shapes are unchanged except for the additive status/timestamp fields.

## Testing constraints (hard)
Backend tests in **new, dedicated** `*ServiceTests.cs` files using the existing **xUnit + Moq** convention (mocked repos, no DB, no running app) covering: legal transition succeeds (A.1/B.3), illegal transition rejected (A.1), admin-only advance (B.4), owner-only cancel-while-Pending (C.5), cancel-not-owner rejected (C.6). Frontend must `npm run build` + `npm run lint` clean; do not modify any pre-existing test file.

## Acceptance (live, full-app boot — backend :5096 + frontend :5173)
- API journeys: admin advances Pending→Processing→Completed (each persists); a non-admin advance → 403; owner cancels a Pending order → Canceled; owner cancel of a Processing order → rejected; cancel of another user's order → 403; an illegal transition → rejected.
- UI journeys (Playwright, per-AC evidence): the customer status tracker renders the order's status; the Cancel button shows only on a Pending owned order and cancelling reflects Canceled; the admin order-management view advances a status and shows it; the admin view is not usable as a regular user.

## Dependency decomposition (for wave execution / R21)
The feature splits cleanly into a dependency DAG: status model + transitions (foundation) → admin advance (depends on status model) → customer cancel (depends on status model) → customer tracker UI (depends on status model + read API) → admin management UI (depends on admin advance). Emit per-BL `**Dependencies:**` / `**Exposes:**` / `**Consumes:**` contracts accordingly.
