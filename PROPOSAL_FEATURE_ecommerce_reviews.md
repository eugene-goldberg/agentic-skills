# Feature proposal — Product Ratings & Reviews (fullstack-ecommerce-app)

> Architect proposal, 2026-06-11. A **new, significant, customer-facing** feature
> for the C#/.NET 8 e-commerce brownfield target, with **new API routes AND a UI
> component**. Every design choice is grounded in the actual codebase (see the
> grounding map in §6) so the crew can implement it by mirroring proven analogs.

---

## 1. The feature, in one paragraph

**Product Ratings & Reviews.** Shoppers can rate a product (1–5 stars) and write a
review; the product page shows the **average rating, a star-distribution bar, and a
paginated list of reviews**, plus an inline **"write / edit / delete your review"**
form; and every **product card** (Home / Collection) shows its average rating so
ratings influence browsing. This is one of the highest-impact features a real
e-commerce site has and the app is **missing the entire experience** today.

## 2. Why this feature (grounded justification)

- **It's a real gap, not a duplicate.** The `Review` entity already exists
  (`Domain/src/Entities/ReviewAggregate/Review.cs` — `ProductId`, `UserId`,
  `Rating:int`, `ReviewText`, `ReviewDate`) and there is a generic
  `ReviewController : AppController<Review,…>` — but there is **no product-scoped
  listing, no aggregate-rating endpoint, no one-review-per-user guard, and NO UI at
  all.** So the feature is genuinely new while resting on a stable entity (low risk).
- **It has a meaty, self-contained UI** — a reusable `StarRating` component (display
  + interactive), a reviews section on the product page, a submission/edit form, and
  an average-rating badge on product cards. Exactly the "API + UI component" the ask
  calls for.
- **It mirrors the proven wishlist analog end-to-end** (entity → repository →
  management → DTOs → controller) so the backend is low-novelty for the crew, and the
  **Cart / Product pages** are the proven frontend analog.
- **It cleanly AVOIDS the known pre-existing defect.** Acceptance FIND-01 flagged
  `POST /api/v1/Carts → 500` (unregistered `ICartManagement` DI) in the cart/pricing
  path. Reviews touch **neither cart nor pricing**, so the sprint won't entangle with
  a pre-existing bug the crew would (correctly) only flag.
- **It deliberately exercises our newest cross-target lesson.** The average rating
  must be computed **server-side once** and read by BOTH the product page AND the
  product cards from the **same summary source** — a textbook instance of the global
  "layer-divergence" lesson (new computation added at one layer while old callers read
  stale/duplicated data). A clean way to see cumulative learning pay off in-sprint.

## 3. API routes (new — all under the existing `api/v1/reviews` versioned prefix)

Mirrors the wishlist's product/user-scoped custom routes layered on `AppController`.

| Method | Route | Purpose | Notable rules |
|---|---|---|---|
| `GET` | `/api/v1/reviews/product/{productId}` | Paginated reviews for a product, newest first; each carries the reviewer's display name + rating + text + date. | `PaginationOptions` query (mirrors products). |
| `GET` | `/api/v1/reviews/product/{productId}/summary` | Aggregate: `averageRating` (1 dp), `totalCount`, `distribution` {5..1 → count}. | Computed via EF `GroupBy(Rating)`. The single source of truth for every average shown. |
| `POST` | `/api/v1/reviews/product/{productId}/user/{userId}` | Submit a review (`rating` 1–5, `reviewText`). | **One review per (user, product)** → `409 Conflict` on duplicate; `rating` out of range → `400`; unknown product/user → `404`. |
| `PUT` | `/api/v1/reviews/{reviewId}/user/{userId}` | Edit own review. | Not the owner → `403`. |
| `DELETE` | `/api/v1/reviews/{reviewId}/user/{userId}` | Delete own review. | Not the owner → `403`. |

*Auth note:* the app has no middleware auth (the wishlist uses explicit
`user/{userId}` path segments). The brief follows that existing convention — `userId`
in the path, ownership checked in the management layer — rather than inventing real
auth (that would be a different, larger feature and a scope violation).

## 4. Domain / persistence (one brownfield migration — a deliberate exercise)

- The `Review` entity already exists; the feature adds a **unique index on
  `(UserId, ProductId)`** (enforce one review per user per product) →
  EF migration `AddReviewUserProductUnique`.
- The migration runs on a **populated DB** via the existing `app_boot.pre_cmd`
  (`dotnet ef database update`) — the brownfield "migration landmine" class the crew
  has handled before. Acceptance Level-3 then verifies the new routes serve.
- *(Stretch, optional BL):* add `HelpfulCount:int default 0` + `POST
  /reviews/{id}/helpful` — a second migration + a "Was this helpful?" UI affordance.

## 5. UI component (React + TS — mirrors Cart/Product page + service patterns)

- **`StarRating` component** (`frontend/src/components/StarRating.tsx`) — two modes:
  read-only (renders ★ fill for a value) and interactive (click/hover to pick 1–5).
  Reused in the list, the form, and product cards.
- **Reviews section on the Product page** (`pages/Product.tsx`):
  - **Summary header** — big average (`★ 4.3 / 5`, `128 reviews`) + a 5-row
    **distribution bar** (5★ ▓▓▓▓░ 60%, …).
  - **Review list** — paginated; each row = `StarRating` (read-only) + reviewer name +
    date + text.
  - **"Write a review" form** — interactive `StarRating` + textarea + submit; on
    success **optimistically** prepends the new review and refreshes the summary. If
    the user already reviewed this product, the form renders in **edit/delete** mode.
- **Average-rating badge on product cards** (Home / Collection) — small read-only
  `StarRating` + count, sourced from the **same `/summary` endpoint** (the
  layer-divergence guard).
- **`services/reviewService.ts`** (axios; mirrors `productService.ts`):
  `fetchProductReviews`, `fetchReviewSummary`, `submitReview`, `updateReview`,
  `deleteReview`. Local component state on the product page (Redux optional — the
  Cart's slice pattern is available if global state is wanted).

## 6. Grounding map (the proven analogs the crew mirrors)

| New layer | Mirror this existing file |
|---|---|
| `IReviewRepository` + `ReviewRepository.GetByProductIdAsync` / `GetSummaryByProductIdAsync` | `Infrastructure/src/Repository/WishlistRepository.cs` (Include/ThenInclude pattern) |
| `IReviewManagement` + `ReviewManagement` (submit/edit/delete/summary, dup-guard) | `Service/src/WishlistService/WishlistManagement.cs` |
| `ReviewReadDto` / `ReviewCreateDto` / `ReviewSummaryDto` | `Service/src/WishlistService/WishlistDtos.cs` |
| `ReviewController` product-scoped + summary routes | `Presentation/src/Controllers/WishlistController.cs` |
| Backend tests `ReviewServiceTests.cs` + `ReviewServiceQaTests.cs` | `Ecommerce.Tests/src/Service/Wishlist*Tests.cs` |
| `reviewService.ts`, `StarRating.tsx`, Product-page section | `services/productService.ts`, `pages/Cart.tsx`, `pages/Product.tsx` |

## 7. Proposed sprint plan (~5 BLs — matches the proven sprint size)

- **BL-0001** — Review repository: product-scoped paginated query (Include reviewer)
  + aggregate-summary query (`GroupBy(Rating)`). Unit tests.
- **BL-0002** — Review management + DTOs: submit (one-per-user `409` guard), edit-own
  (`403`), delete-own, summary. The `(UserId, ProductId)` unique-index migration.
  Unit tests.
- **BL-0003** — `ReviewController` product-scoped + summary routes; validation
  (`400`/`404`). Controller/integration tests.
- **BL-0004** — Frontend: `StarRating` component + `reviewService` + Product-page
  Reviews section (summary header, list, submit/edit/delete form, optimistic update).
- **BL-0005** — Frontend: average-rating badge on product cards (Home/Collection)
  sourced from `/summary`; wiring.

**Acceptance (whole-feature E2E):** API journeys — submit → list → summary → edit →
delete → duplicate-`409` → non-owner-`403`; **Playwright UI journey** — open a
product, see the average + distribution, write a review with the star input, watch it
appear and the summary update, edit it, delete it, then see the average on a product
card. Plus the one full pre-existing-suite regression checkpoint.

## 8. Calibrated proposal (risk / proof / rollback)

- **Risk: low–medium.** Additive (new routes, new UI, one additive migration); rests
  on an existing entity; avoids the known FIND-01 cart bug. The only real risk is the
  populated-DB migration — mitigated by the `app_boot pre_cmd` + acceptance Level-3
  route check (proven on this target).
- **Named test that proves benefit:** the acceptance E2E above — specifically the
  Playwright journey writing a review and seeing it reflected in BOTH the product-page
  summary AND a product-card badge (proves the end-to-end feature *and* the
  layer-divergence guard).
- **Named rollback:** the feature is isolated — revert the sprint's merge on
  `integration`; the new routes/UI/migration are self-contained and touch no existing
  behavior (the generic `ReviewController` CRUD and all other features are untouched).

## 9. Alternative considered (not recommended as the first pick)

**Discount / coupon codes** (net-new entity + checkout "apply code" UI + admin
create-code UI) is also significant and is a *perfect* thematic fit for the
layer-divergence lesson. **But** it must compute discounted cart/order totals — i.e.
it lives in the **cart/pricing path that carries the known FIND-01 `500` bug**, so the
sprint would likely collide with a pre-existing defect (which the crew would flag, not
fix). Better as a *follow-on* once FIND-01 is addressed. Ratings & Reviews gives a
cleaner, equally-significant first demonstration.
