# Proposal — next brownfield feature: **Inventory & Stock Enforcement**

> Target: `fullstack-ecommerce-app` (C#/.NET 8 + EF Core + Postgres + React/TS),
> branch `integration`. Proposed 2026-06-13 by the architect, grounded in the live
> codebase. Status: **LOCKED 2026-06-13** — scope frozen to forward stock enforcement
> (decrement-on-placement); restock-on-cancel explicitly OUT of scope (see §D-note),
> verified against the live aggregate. Ready to convert to a launch payload.

## One-liner

Wire **stock/inventory enforcement** into the order lifecycle: a product cannot be
ordered beyond its available quantity, placing an order **decrements** stock, and the
storefront reflects availability — using the inventory primitives the domain model
**already exposes but never calls.**

## Why this is the right next crew test (what the crew gains)

Three capability probes, each calibrated against a known frontier:

1. **Grounded reuse vs. reinvention (the "layer-divergence" lesson, live).**
   `Product` already carries `int Quantity` and two domain methods —
   `IsInStock()` (`return Quantity > 0`) and `UpdateStock(int)` (with an
   oversell guard) — but a repo-wide search shows **they are referenced nowhere**
   in `Ecommerce.Service` / `Ecommerce.Controller` / `Ecommerce.Infrastructure`.
   They are written-but-unwired dead code. A competent engineer discovers and
   *uses* them; a weak crew reinvents a parallel stock path (the exact
   cross-target failure mode our global lessons warn about:
   *"new core/API computation exists but consumers still call the legacy path"*).
   This feature **directly exercises** that lesson and the Pattern-Fidelity rubric.

2. **Safely modifying a sensitive core path.** The reviews feature deliberately
   said *"do NOT touch cart/pricing/checkout."* This feature **requires** touching
   the order-placement path. It's the natural escalation: can the crew modify the
   `OrderService.Create` path and add an invariant **without regressing** the
   existing order/cart/payment suite? Regression Coverage + Invariant Preservation
   + Blast Radius are all under test here.

3. **Un-telegraphed concurrency correctness (a discovery probe, à la Exp-1b).**
   `UpdateStock`'s in-memory guard is **not** concurrency-safe across two
   simultaneous requests for the last unit. The brief states the invariant
   ("stock never goes negative; orders never oversell") **without prescribing**
   optimistic concurrency / a transactional check / a DB constraint. Whether the
   crew discovers it needs one is the "would a senior engineer get it right?" test.

## The brief (runnable — WHAT must be true and testable, not HOW)

**Context:** `Product` has `Quantity`, `IsInStock()`, `UpdateStock(int)` (currently
unused); `OrderItem` carries `ProductId` + `Quantity`; an `OrderService` /
`OrderItemService` already create orders. Build inventory enforcement on top of the
**existing** order aggregate and Product model, mirroring existing aggregate patterns
(domain method → repository → service + DTO → controller → xUnit/Moq service tests for
backend; existing product/cart pages + axios services + reusable components for
frontend). Do **not** rewrite the generic AppController/BaseService machinery, auth,
the pricing/payment math, or the DbContext base wiring beyond what this feature needs.

**A. Stock as the single source of truth**
1. A product exposes its **available quantity** through the API (read), and the
   storefront reads availability from that single server value — not a second
   client-side computation.
2. `IsInStock()` / `UpdateStock(int)` (or an equivalent already-present primitive)
   are the **only** place stock is mutated/queried — no parallel stock arithmetic
   added elsewhere.

**B. Order placement enforces and decrements stock**
3. Placing an order whose line quantity exceeds the product's available quantity is
   **rejected with a client error and no state change** (no order created, no partial
   decrement).
4. A successfully placed order **decrements** each product's available quantity by the
   ordered amount, exactly once.
5. A multi-line order is **all-or-nothing**: if **any** line is short, the whole order
   is rejected and **no** product's stock changes (no half-applied orders).
6. Two concurrent attempts to buy the last available unit(s) must **never** oversell —
   at most the available quantity is sold; the loser gets the client error. (The
   invariant: persisted `Quantity` is never negative.)

**C. Storefront reflects availability**
7. Product cards and the product-detail page show an **out-of-stock / N-left** state
   sourced from the same availability value (A.1).
8. The add-to-cart / quantity control is **disabled or capped** at the available
   quantity for an out-of-stock or low-stock product; an out-of-stock product cannot
   be added to the cart from the UI.

**D-note — restock-on-cancel is OUT OF SCOPE (verified 2026-06-13).** The order
aggregate has an `OrderStatus.Canceled` value and `Order.UpdateOrderStatus(...)`, but
**no first-class cancellation flow exists**: there is no cancel endpoint, no cancel
service method, and no transition rules (`grep -ni cancel` across Service/Controller is
empty; `OrderController` exposes only read queries). Building restock-on-cancel would
require first building the entire cancellation lifecycle (endpoint + authz + allowed
transitions) — a separate feature on the sensitive order path. This feature is
**decrement-only on order placement.** It is acknowledged and accepted that cancelling
an order (via the generic status update that exists today) does **not** restock — that
is pre-existing behavior and the subject of a future "order cancellation lifecycle"
feature, not a defect of this one. The crew MUST NOT build a cancellation flow here.

**E. Preservation (non-negotiable)**
9. Every existing feature — products, cart, orders, payments, users, auth, wishlist,
   reviews — behaves exactly as today; all existing tests pass; response shapes for
   existing endpoints are unchanged except for the additive availability field.

**Testing constraints (hard):** backend tests in **new, dedicated** `*ServiceTests.cs`
files using the existing **xUnit + Moq** convention (mock repositories, no DB, no
running app) covering: reject-over-quantity (B.3), decrement-on-success (B.4),
all-or-nothing multi-line (B.5), and the oversell/negative-stock guard (B.6). Frontend
must `npm run build` + `npm run lint` clean. Do **not** modify or append to any
pre-existing test file.

**Acceptance (live, full-app boot — backend :5096 + frontend :5173):**
API journeys: read a product's availability; order within stock → succeeds and the
availability drops by the ordered amount; order beyond stock → rejected, availability
unchanged; multi-line order with one short line → rejected, **no** stock moved. UI
journeys (Playwright, per-AC evidence): out-of-stock badge renders; add-to-cart
disabled/capped for an out-of-stock product.

## Falsifiable failure predictions (the experiment design)

- **P1 (reinvention):** crew adds a new stock field/computation instead of using
  `Quantity`/`IsInStock`/`UpdateStock` → Pattern-Fidelity fail; the layer-divergence
  lesson did **not** transfer.
- **P2 (no atomicity):** multi-line short order half-decrements stock (B.5 fails) →
  missing transactional boundary.
- **P3 (oversell race):** concurrent last-unit orders both succeed (B.6 fails) → crew
  shipped a check-then-act race; did not discover concurrency control.
- **P4 (UI-only enforcement):** crew enforces stock only in the frontend, backend still
  oversells → trust-boundary defect (mirrors the reviews 401 class: real rule must live
  server-side).
- **P5 (regression):** existing order/payment tests break → blast-radius miscontrol on a
  sensitive path.

Each prediction has a direct acceptance journey or unit test that would catch it — so a
clean live-acceptance run is a real signal, not a vacuous pass.

## Risk · proof · rollback (architect calibration)

- **Risk:** touches the order-placement path (core); a bad change could regress
  checkout. Mitigated by E.9 preservation + the one acceptance-phase full regression
  run + per-BL scoped tests.
- **Named proof of benefit:** the live-acceptance loop reaches `loop.accepted` with the
  B.3/B.4/B.5/B.6 API journeys green against the booted app **and** the pre-existing
  `dotnet test` suite stays green at the regression checkpoint.
- **Rollback:** feature lands on agent worktrees → `integration`; revert is the merge
  commit(s). No baseline-auth or pricing changes expected; if the crew proposes one, it
  surfaces as an explicit operator scope decision (per `feedback_baseline_auth_inscope`).

## Alternatives considered (lower priority)

- **Review-helpfulness voting** — builds on the just-shipped reviews (cumulative test),
  but isolated/low-risk; doesn't probe the core-path or concurrency frontier.
- **Order status lifecycle / fulfillment state machine** — good authz + state-transition
  test, but no equivalent "unwired primitive already present" grounding hook.
- **Coupon/discount at checkout** — strong pricing-correctness test, but overlaps the
  already-drafted cart-discount architect-agent brief; defer to avoid duplication.
