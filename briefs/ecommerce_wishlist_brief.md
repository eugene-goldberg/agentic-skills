Add a "Wishlist" (Favorites) capability so a signed-in user can save products
they are interested in for later, view their saved products, remove them, and move
a saved product into their shopping cart.

Context: The app already has a shopping Cart (a user has one Cart; a Cart has many
CartItems; each CartItem references a Product and carries a quantity). A Wishlist
is the natural sibling of the Cart: a user has one Wishlist; a Wishlist has many
items; each item references a Product. Build the Wishlist by following the existing
Cart aggregate's patterns end-to-end — the domain entity + repository, the service
layer + DTOs, the API controller, and the unit-test conventions — so the new code
is consistent with the codebase it lives in. This is ordinary business logic over
the existing model and HTTP API; do not modify, refactor, or "improve" the data-
access plumbing, the DbContext base wiring, the generic AppController/BaseService
machinery, auth, or any other infrastructure beyond what adding one new aggregate
requires.

Requirements (product behavior — design the implementation from the actual
codebase; the points below are WHAT must be true and testable, not HOW):

A. The wishlist
   1. A user has a single wishlist. The API can return a given user's wishlist
      together with its items, where each item identifies the saved Product.
   2. A user can add a Product to their wishlist, and can remove a previously
      saved Product from their wishlist.

B. Uniqueness (a wishlist is a SET of products, not a quantity list)
   3. A given Product appears AT MOST ONCE in a user's wishlist. Adding a Product
      that is already in the wishlist must NOT create a second entry — adding an
      already-present product is either a no-op success or a client error
      (your choice), but it must never produce a duplicate. This rule must be
      enforced in the application/service logic, not only by a database
      constraint.
   4. Adding a Product that does not exist is rejected with a client error and no
      state change.

C. Move to cart
   5. A user can move a saved item from their wishlist into their shopping cart in
      one operation: the product is added to the user's Cart using the EXISTING
      cart logic/abstractions (do not reimplement cart behavior), AND the item is
      removed from the wishlist. The result must be consistent — after a
      successful move the product is in the cart and is no longer in the wishlist;
      a partial outcome (in both, or in neither) is a defect.

D. Preservation (non-negotiable)
   6. Every existing feature — cart, orders, products, reviews, payments, users,
      auth, etc. — must behave EXACTLY as it does today. Adding the wishlist must
      not change any existing endpoint, response shape, or behavior, and all
      existing tests must continue to pass.

SCOPE — BACKEND ONLY:
   This work is the .NET backend only: the domain entity/entities, EF Core
   persistence + the migration, the service + DTOs, the API controller, and unit
   tests. Do NOT touch the React frontend in this sprint — no frontend pages,
   components, services, or Redux. A wishlist UI is a separate later effort.

TESTING CONSTRAINTS (hard requirements — the gate depends on them):
- Write your tests with the project's existing test stack (xUnit + Moq) and follow
  the existing service-test convention — see
  backend/Ecommerce.Tests/src/Service/CartItemServiceTests.cs and
  ProductServiceTests.cs as the model: construct the service with MOCKED
  repositories (Moq), exercise the service methods, assert behavior and verify the
  expected repository calls. The tests must run under `dotnet test` with NO
  database and NO running app (mocks only) — exactly like the existing service
  tests.
- Put ALL of your new tests in brand-new, dedicated test files named for this
  feature (e.g. backend/Ecommerce.Tests/src/Service/WishlistServiceTests.cs). You
  may add more than one new test file, but every new test file must be NEW and
  wishlist-specific.
- Do NOT modify, append to, or wholesale-import any of the application's
  pre-existing test files. Cover both the success and the failure/edge paths
  (uniqueness on duplicate add per (B.3), non-existent product per (B.4), and the
  move-to-cart consistency per (C.5)).

Acceptance: the feature must be verifiable end-to-end through the HTTP API.
Demonstrate: a user can add products to their wishlist and read them back; adding
the same product twice does not create a duplicate; adding a non-existent product
is rejected; removing a product works; and moving a saved item to the cart leaves
the product in the cart and absent from the wishlist. No UI verification is in
scope for this sprint.
