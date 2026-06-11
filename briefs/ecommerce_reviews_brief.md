Add a "Product Ratings & Reviews" capability so a user can rate a product (1–5
stars) and write a review, and so every shopper can see a product's average rating,
its rating breakdown, and the list of reviews — both on the product detail page and
as a rating badge on product cards while browsing.

Context: The app already has a Review entity (a Review references a Product and a
User and carries an integer Rating and review text) and a generic CRUD controller
for it, but there is NO product-scoped review listing, NO aggregate-rating endpoint,
and NO user-facing UI. This feature builds the complete reviews experience on top of
the EXISTING Review entity. Build it by following the existing aggregates' patterns
end-to-end — mirror the Wishlist aggregate (domain entity + repository, service +
DTOs, API controller, xUnit/Moq service-test conventions) for the backend, and
mirror the existing product/cart pages + axios service files for the frontend — so
the new code is consistent with the codebase it lives in. This is ordinary business
logic over the existing model and HTTP API plus a self-contained React UI; do NOT
modify, refactor, or "improve" the data-access plumbing, the DbContext base wiring,
the generic AppController/BaseService machinery, auth, the cart/pricing/checkout
path, or any other infrastructure beyond what this feature requires.

Requirements (product behavior — design the implementation from the actual codebase;
the points below are WHAT must be true and testable, not HOW):

A. Reviews — read
   1. The API can return the reviews for a given Product, most-recent first, with
      pagination, where each review carries its star rating, its text, the date, and
      the reviewer's display name.
   2. The API can return a rating SUMMARY for a given Product: the average rating
      (to one decimal), the total number of reviews, and the count of reviews at
      each star level (how many 5-star, 4-star, 3-star, 2-star, 1-star).
   3. The average rating shown anywhere in the UI MUST come from this single summary
      source — the product detail page and the product-card badge must both read the
      same server-computed summary. Do NOT compute an average a second way in the
      frontend or in any other endpoint. (This prevents the classic "new computation
      added at one layer while another surface still derives its own value" defect.)

B. Reviews — write
   4. A signed-in user can submit a review for a Product: a star rating in the range
      1–5 and review text. A rating outside 1–5 is rejected with a client error and
      no state change; a review for a non-existent product is rejected with a client
      error and no state change.
   5. A user may have AT MOST ONE review per Product. Submitting a second review for
      a product the user has already reviewed must NOT create a duplicate — it is
      either rejected with a client error or treated as an update (your choice), but
      it must never produce two reviews by the same user for the same product. This
      rule must be enforced in the application/service logic, not only by a database
      constraint.
   6. A user can EDIT their own review (change the rating and/or text) and can DELETE
      their own review. A user must NOT be able to edit or delete a review that is
      not theirs — such an attempt is rejected with a client error and no state
      change.

C. The UI
   7. On the product detail page, a shopper sees: the product's average rating and a
      star-level breakdown bar, and a paginated list of the product's reviews (each
      with stars, reviewer name, date, text).
   8. A signed-in user sees an inline "write a review" control on the product detail
      page (a star picker + a text field) that submits a review and reflects the
      result without a full page reload; if the user has already reviewed the
      product, that control instead lets them edit or delete their existing review.
   9. On product cards in the browsing/listing views, each product shows its average
      rating (stars + review count) sourced from the same summary endpoint (per A.3).
   10. Provide a single reusable star-rating UI element used by the list, the write
       control, and the product-card badge (a read-only display mode and an
       interactive pick mode), rather than three separate star implementations.

D. Preservation (non-negotiable)
   11. Every existing feature — products, cart, orders, payments, users, auth,
       wishlist, the existing generic review CRUD, etc. — must behave EXACTLY as it
       does today. Adding ratings & reviews must not change any existing endpoint,
       response shape, page, or behavior, and all existing tests must continue to
       pass. Do NOT touch the cart/pricing/checkout code.

SCOPE — backend API + frontend UI (both):
   - Backend (.NET): the repository query methods, the service + DTOs, the API
     controller routes, the EF Core migration for the one-review-per-(user,product)
     rule, and xUnit/Moq service unit tests.
   - Frontend (React/TS): the reusable star-rating component, the product-detail
     reviews section (summary + list + write/edit/delete control), the product-card
     rating badge, and the axios service that calls the new endpoints. Follow the
     existing pages/components/services conventions; do NOT add a new state library
     or restructure routing.

TESTING CONSTRAINTS (hard requirements — the gate depends on them):
- BACKEND: write your tests with the project's existing test stack (xUnit + Moq) and
  follow the existing service-test convention — see
  backend/Ecommerce.Tests/src/Service/WishlistServiceTests.cs (and the CartItem /
  Product service tests) as the model: construct the service with MOCKED repositories
  (Moq), exercise the service methods, assert behavior, and verify the expected
  repository calls. The tests must run under `dotnet test` with NO database and NO
  running app (mocks only), exactly like the existing service tests. Cover both
  success and failure/edge paths: rating out of range (B.4), non-existent product
  (B.4), one-review-per-user on duplicate submit (B.5), edit/delete by non-owner
  rejected (B.6), and the summary aggregation (A.2).
- Put ALL of your new backend tests in brand-new, dedicated test files named for this
  feature (e.g. backend/Ecommerce.Tests/src/Service/ReviewServiceTests.cs). You may
  add more than one new test file, but every new test file must be NEW and
  review-specific. Do NOT modify, append to, or wholesale-import any pre-existing
  test file.
- FRONTEND: the new React code must type-check and build cleanly (`npm run build`)
  and pass lint (`npm run lint`) with no new errors. The frontend has no automated
  test runner configured; verify your UI by building it and by confirming it calls
  the real endpoints you implemented. Keep the UI self-contained to the files this
  feature adds/edits.

ACCEPTANCE (how the assembled feature is verified end-to-end):
- API journeys (always, against the running backend): submit a review and read it
  back in the product's review list; the summary reflects the new review (average,
  count, per-star breakdown); submitting a second review for the same product by the
  same user does not create a duplicate; a rating outside 1–5 is rejected; a review
  for a non-existent product is rejected; editing and deleting one's own review work;
  editing/deleting another user's review is rejected.
- UI: the product-detail reviews section and the product-card badge are delivered and
  build cleanly. NOTE: automated browser (Playwright) verification of the UI requires
  the frontend to be booted alongside the backend, which the current acceptance app
  boot does not yet do (it boots the backend only); a full UI click-through E2E is
  therefore out of automated scope for this sprint and is verified by the API
  journeys above plus a clean frontend build. (Booting the frontend for acceptance is
  a known follow-up capability.)
