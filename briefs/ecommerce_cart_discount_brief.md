Add cart-level discount codes to the shopping experience: a user can apply a
discount code to their cart, the cart's total is reduced by the discount, and the
discount is shown allocated across the cart's line items so each line displays its
fair share of the savings.

Context: The app already has a Cart with CartItems; each CartItem references a
Product and carries a Quantity, a UnitPrice, and a line TotalPrice
(`decimal(10,2)`). Money throughout the app is `decimal(10,2)` — i.e. whole cents.
Build this feature by following the existing Service-layer patterns end-to-end (a
management/service class + DTOs + an API controller + xUnit/Moq service unit tests),
mirroring the existing aggregates (e.g. the Wishlist/CartItem services). This is
ordinary business logic over the existing model and HTTP API. Do NOT modify,
refactor, or "improve" the generic AppController/BaseService/BaseRepository
machinery, the DbContext wiring, auth, or — importantly — the existing
cart-creation / cart-controller path; build the discount logic as its own
service-layer capability so it can be unit-tested with mocked repositories.

Requirements (product behavior — design the implementation from the actual
codebase; the points below are WHAT must be true and testable, not HOW):

A. The discount
   1. A discount code carries a discount AMOUNT expressed as a whole-cent money
      value (e.g. $10.00 off) applied to a cart. (A simple fixed-amount code is in
      scope; percentage codes are not required for this feature.)
   2. Given a cart with its line items, the feature computes the cart's pre-discount
      total (the sum of the line TotalPrices) and the post-discount total
      (pre-discount total minus the discount amount, floored at zero).

B. Per-line allocation (the core of this feature)
   3. The discount must be ALLOCATED ACROSS THE CART'S LINE ITEMS in proportion to
      each line's pre-discount TotalPrice, so every line carries its fair share of
      the savings and the UI can show a per-line discounted subtotal.
   4. Every per-line allocated discount MUST be a whole-cent money value
      (`decimal(10,2)`, no fractional cents) — the app never stores or displays a
      sub-cent amount.
   5. **Exact-sum invariant (non-negotiable):** the sum of the per-line allocated
      discounts MUST EQUAL the total discount amount EXACTLY — not a cent more, not
      a cent less. No penny may be created or lost in the allocation. This must hold
      for EVERY cart, including carts whose proportional shares do not divide evenly
      into whole cents.
   6. The allocation must be deterministic (the same cart + same code always
      produces the same per-line split) and stable (it must not depend on the
      order line items happen to be iterated in, beyond a defined tie-break).

C. Edge behavior
   7. A discount larger than the cart's pre-discount total reduces the cart to a
      zero total (the post-discount total is floored at zero) and the per-line
      allocated discounts still sum exactly to the discount actually applied (i.e.
      the pre-discount total in that case). Applying a code to an empty cart is a
      no-op success.

D. Preservation (non-negotiable)
   8. Every existing feature — products, cart, cart items, orders, payments, users,
      auth, wishlist, reviews — must behave EXACTLY as it does today. Adding the
      discount capability must not change any existing endpoint, response shape, or
      behavior, and all existing tests must continue to pass. Do NOT touch the
      cart-creation / cart-controller path or the generic base machinery.

SCOPE — backend service + API:
   The .NET backend: the discount/allocation service + its DTOs, an API surface to
   apply a code to a cart and read back the allocated result, any small domain
   addition the discount code needs, and xUnit/Moq service unit tests. No frontend
   work is in scope for this feature.

TESTING CONSTRAINTS (hard requirements — the gate depends on them):
- Write your tests with the project's existing stack (xUnit + Moq) following the
  existing service-test convention — construct the service with MOCKED repositories,
  exercise the service methods, and assert behavior. Tests must run under
  `dotnet test` with NO database and NO running app (mocks only), exactly like the
  existing service tests (see WishlistServiceTests.cs / CartItemServiceTests.cs).
- Put ALL new tests in brand-new, dedicated, feature-specific test files. Do NOT
  modify or append to any pre-existing test file.
- Your tests MUST cover the allocation invariants directly and adversarially, NOT
  just a happy path. In particular you MUST include cases where the proportional
  shares do NOT divide evenly into whole cents, and assert BOTH that every per-line
  allocated discount is a whole-cent value AND that the per-line discounts sum
  EXACTLY to the total discount (B.4 + B.5). Examples to cover: a $10.00 discount
  split across three equal lines; a discount across lines with unequal totals whose
  proportional shares land on half-cents; the over-discount case (C.7). These cases
  are the real test of the feature — a naive implementation that rounds each line's
  proportional share independently will FAIL the exact-sum invariant, and that is
  exactly what your tests must catch.

Acceptance: the feature is verifiable end-to-end through the service/API: a discount
code applied to a cart yields a correct post-discount total and a per-line
allocation in which every line is whole-cent and the lines sum EXACTLY to the
discount, for ordinary carts and for carts whose shares don't divide evenly into
cents. Existing features remain unchanged.
