---
run_id: run-20260524T014937Z-e74aff
project_name: api-keys-feature
repo: full-stack-fastapi-template
started_at: 2026-05-24T01:49:37.013918+00:00
brief_hash: 901ed052644bdbbbbe8f678427bbe1fcd016bf137778c0158ac62529184117e8
backfilled: true
backfill_note: A17 persistence landed mid-RBAC-sprint; this brief was POSTed inline before A17 existed. Re-created from /tmp/api-keys-brief.md for archive completeness.
---

Add a personal API key system to the application. Users (with the appropriate role) can create, list, and revoke API keys associated with their account. Each API key is a long, opaque token that can be used to authenticate programmatic requests as an alternative to the existing session/JWT flow.

Requirements:

1. **Data model**: a new `ApiKey` table associated with a user. Columns at minimum: id (UUID), user_id (FK), name (user-supplied label), token_hash (the secret is hashed at rest, never stored in cleartext), prefix (the first ~8 chars of the secret, shown in UI for identification), created_at, last_used_at (nullable), revoked_at (nullable). A user can have multiple API keys.

2. **Backend endpoints** under the existing API prefix and following the repo's existing FastAPI router conventions:
   - `POST /api/v1/users/me/api-keys` — create a new key. Returns the cleartext secret exactly once in the response; subsequent reads only show the prefix.
   - `GET  /api/v1/users/me/api-keys` — list the current user's keys (name, prefix, created_at, last_used_at, revoked_at).
   - `DELETE /api/v1/users/me/api-keys/{id}` — revoke a key (set revoked_at; do not hard-delete, for audit trail).
   - Bearer-token auth in the existing security layer: if the `Authorization: Bearer <token>` header carries an active API key (not a JWT), the request is authenticated as that key's user. Revoked or non-existent keys → 401.

3. **Frontend** following the existing TanStack-Router + Chakra UI conventions in the template:
   - New route under the authenticated layout: `/api-keys` (or whatever fits the repo's pattern).
   - List view of the user's keys with name, prefix, created_at, last_used_at, a status badge (active / revoked), and a revoke button.
   - Create modal: name input, submit, then a one-time display of the freshly generated secret with a copy button and a clear warning that this is the only time it will be shown.
   - Empty state when the user has no keys.

4. **Tests**:
   - Backend pytest tests covering create / list / revoke / auth-with-key / auth-with-revoked-key.
   - Playwright e2e covering: login → navigate to API keys page → create → see one-time secret → revoke → confirm revoked badge appears.

5. **Migration**: an Alembic migration for the new table, following the existing migration conventions.

6. **Security**: do not log raw API keys. Hash with the project's existing password-hashing approach (or sha256 if password hashing is asymmetrically slow for per-request lookup; document the trade-off in the PR). Generate tokens with `secrets.token_urlsafe`.

Scope it as a normal feature increment, not a security hardening pass. Match the existing code patterns (repository layer, error handling, response shapes, frontend mutation/query hooks).
