# UI tour — operator-side visual inspection

## Purpose

The brownfield regression gate verifies functional correctness via playwright
(navigates routes, clicks buttons, fills forms, asserts DOM state). It does
NOT capture screenshots — a layout regression that doesn't break click
selectors will pass green.

This tool fills that gap. It takes the current state of a feature branch,
boots an isolated docker stack, drives playwright through every important
route (login, signup, dashboard, items, time, settings, admin), captures a
full-page screenshot of each, snaps the "Add X" dialog if one exists, and
preserves the PNGs under
`webapp/backend/screenshots/<repo>-<branch>-<ts>/` with absolute paths
printed at the end.

## Usage

```bash
# Default: time-tracking branch on full-stack-fastapi-template
tools/ui_tour/ui_tour.sh

# Or pin a specific branch + repo
tools/ui_tour/ui_tour.sh <branch> <repo>
```

Safe to run while a sprint is in flight:
- Uses `git worktree add` to a sandbox dir under `/tmp` — does not touch
  the orchestrator's working tree.
- Uses a unique `COMPOSE_PROJECT_NAME` per run so the temporary stack
  doesn't collide with the gate's stacks.
- Cleanup runs on every exit path (success, error, Ctrl-C) via trap.

## What you get

Files in `webapp/backend/screenshots/<repo>-<branch>-<ts>/`:
- `00_login.png` etc. — full-page snapshots of public routes
- `10_dashboard.png` etc. — authed routes (logged in as a freshly-created
  user)
- `10_dashboard_dialog_open.png` etc. — if the route has a primary
  "Add …" button, an additional snapshot with the dialog open

Open them with:
```bash
open webapp/backend/screenshots/<dir>/*.png
```

## Extending the route list

Edit `_tour_template.spec.ts` and append to `PUBLIC_ROUTES` or
`AUTHED_ROUTES`. Each entry is `{ path: "/route", name: "stable_slug" }`.

The slug becomes the filename. Keep them stable so before/after diffs make
sense across runs.

## Future: durable harness integration

The `_tour_template.spec.ts` and `playwright.tour.config.ts` are also
candidates for inclusion in `webapp/backend/app/templates/` so that
`POST /api/projects/{repo}/init-feature` ships every new feature branch
with a built-in tour spec. Deferred until validated on at least one
real sprint.
