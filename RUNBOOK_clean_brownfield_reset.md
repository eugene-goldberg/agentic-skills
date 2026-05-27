# RUNBOOK — Clean Brownfield Reset

> Procedure to launch a new brownfield feature run against a target repo
> that has already hosted a prior feature sprint, with **no
> cross-contamination** from the prior run's code, artifacts, retrieval
> indexes, or orchestrator state.
>
> Worked example uses `full-stack-fastapi-template` after the
> `documents_1` sprint, preparing for a `documents_2` submission. The
> same steps apply to any (target, prior_feature, new_feature) triple.

---

## Why this exists

The brownfield pipeline shares state across runs through several
surfaces that are **not** keyed by `feature_key`:

| Surface | Keyed by | Cross-contamination risk |
|---|---|---|
| `agent_branch` (target repo) | branch name in `.agentic-skills.json` | new run sees prior feature's merged code as "the codebase" |
| `_brownfield/` in target | BL id only | overwrites or shadows prior BL artifacts |
| Graphify cache | `sha256(repo_path)[:16]` | serves nodes that no longer exist on a reset branch |
| claude-context Milvus collection | repo path | same — stale embeddings of removed code |
| `agent/<task_id>` worktrees & branches | task_id | I-3 closure not yet enforced; leftovers accumulate |
| `.orchestrator-state/*.json` | run_id | stale `live/` entries confuse RECOVERY playbook |
| `logs/orchestrator/.latest` | symlink | A33 — points at prior run |
| Docker test stack | container names | seeded DB state carries between runs |

PO's Codebase Intelligence Protocol (doctrine v1.1) leans heavily on
graphify + claude-context. If those indexes still describe the prior
feature, PO writes a sprint plan that "knows" code which is no longer
present on the agent branch — the resulting backlog will be incoherent
or partially no-op.

---

## Preconditions

- All prior-feature runs are terminated (no `live/` orchestrator state
  for the target repo).
- Operator has approved a `feature_key` for the new run.
- Operator has decided whether to **reset** `agent_branch` or **fork** a
  new agent branch. Recommended: fork. Preserves prior history for
  comparison; cheaper to roll back.

---

## Variables

Set once at the top of the session:

```bash
TARGET_REPO=full-stack-fastapi-template
TARGET_PATH=~/dev/ai-projects/brownfield-targets/$TARGET_REPO
PRIOR_FEATURE=documents_1
NEW_FEATURE=documents_2
NEW_AGENT_BRANCH=agentic-skills-work-${NEW_FEATURE}
MAIN_REF=master   # from .agentic-skills.json::main_ref
REPO_SHA=$(printf '%s' "$TARGET_PATH" | shasum -a 256 | cut -c1-16)
```

---

## Step 1 — Fork a fresh agent branch off `main_ref`

```bash
cd "$TARGET_PATH"
git fetch origin
git checkout "$MAIN_REF"
git pull --ff-only
git checkout -b "$NEW_AGENT_BRANCH"
git push -u origin "$NEW_AGENT_BRANCH"
```

Update `.agentic-skills.json` at target root:

```json
{
  "agent_branch": "agentic-skills-work-documents_2",
  "main_ref": "master",
  "doctrine": "brownfield"
}
```

Commit and push that change on `$NEW_AGENT_BRANCH`.

**Verify:** `git log --oneline -5` shows only `$MAIN_REF` history plus
the `.agentic-skills.json` edit. No `BL-0001..BL-000N` commits from the
prior feature should appear.

---

## Step 2 — Strip `_brownfield/` from the new branch

```bash
cd "$TARGET_PATH"
git checkout "$NEW_AGENT_BRANCH"
rm -rf _brownfield/
git add -A
git commit -m "chore: clear _brownfield/ for fresh ${NEW_FEATURE} run"
git push
```

If `_brownfield/` is not present on `$MAIN_REF`, this is a no-op — skip
the commit but verify the directory is absent.

---

## Step 3 — Prune stale agent worktrees and branches

```bash
cd "$TARGET_PATH"
git worktree list
# For each agent/<task_id> entry not currently in use:
git worktree remove <path>
git worktree prune

# Then drop the dead local branches:
git branch | grep '^\s*agent/' | xargs -n1 git branch -D
```

Do **not** delete branches from remote unless the operator confirms the
prior run is fully archived.

---

## Step 4 — Purge graphify cache for this repo

```bash
GRAPHIFY_DIR=~/.cache/agentic-skills/graphify/$REPO_SHA
ls -la "$GRAPHIFY_DIR" 2>/dev/null && rm -rf "$GRAPHIFY_DIR"
```

The next graphify call from the orchestrator will rebuild against the
fresh `$NEW_AGENT_BRANCH` tree.

Also verify no stale `graphify-out` symlink lingers in the target's
working tree (A35 fix should keep `.gitignore` honoring this):

```bash
cd "$TARGET_PATH"
ls -la graphify-out 2>/dev/null && rm graphify-out
```

---

## Step 5 — Drop the claude-context Milvus collection

Collection naming convention follows the bridge in
`.spike-node/bridge.js`. From the webapp host (with local Milvus
running):

```bash
cd ~/dev/ai-projects/agentic-skills/webapp/backend
# List collections to confirm name
python -c "
from pymilvus import connections, utility
connections.connect(alias='default', host='127.0.0.1', port='19530')
print(utility.list_collections())
"

# Drop the one matching this repo (name typically derived from repo path)
python -c "
from pymilvus import connections, utility
connections.connect(alias='default', host='127.0.0.1', port='19530')
utility.drop_collection('<collection_name_for_target>')
"
```

If the indexer auto-rebuilds collections on first call, dropping is
sufficient — no manual re-create needed.

---

## Step 6 — Sweep orchestrator state

```bash
cd ~/dev/ai-projects/agentic-skills/webapp/backend
ls .orchestrator-state/

# Move any live/*.json belonging to prior $TARGET_REPO runs to done/
# (jq filter on repo field, or grep by feature_key)
for f in .orchestrator-state/live/*.json; do
  if grep -q "\"feature_key\":\s*\"${PRIOR_FEATURE}\"" "$f" 2>/dev/null; then
    mv "$f" .orchestrator-state/done/
  fi
done
```

Confirm nothing related to the prior feature remains in `live/`.

---

## Step 7 — Archive prior traces and fix `.latest` symlink

```bash
cd ~/dev/ai-projects/agentic-skills/webapp/backend
mkdir -p traces_archive
mv "traces/${TARGET_REPO}" "traces_archive/${TARGET_REPO}-${PRIOR_FEATURE}-$(date +%Y%m%d)"

# Repair A33 stale .latest in orchestrator logs
LATEST=logs/orchestrator/.latest
[ -L "$LATEST" ] && rm "$LATEST"
# (Will be re-pointed by the next run's TraceWriter.)
```

---

## Step 8 — Restart the test-environment Docker stack

```bash
cd "$TARGET_PATH"
docker compose down -v        # -v wipes seeded DB volumes
docker compose up -d backend frontend db mailcatcher playwright
docker compose ps             # confirm all healthy
```

`-v` is intentional — seeded test data from the prior sprint can shift
gate outcomes (especially on permission / workspace-isolation BLs).

---

## Step 9 — Confirm `feature_key` is unused

```bash
cd ~/dev/ai-projects/agentic-skills
grep -r "${NEW_FEATURE}" webapp/backend/.orchestrator-state/ \
    webapp/backend/traces/ \
    webapp/backend/traces_archive/ \
    2>/dev/null || echo "clean"
```

Expect `clean`. Any match is a collision and must be renamed before
submission.

---

## Step 10 — Launch

Submit through the webapp UI or directly:

```bash
curl -X POST "http://localhost:8000/api/projects/${TARGET_REPO}/run-brief" \
  -H 'Content-Type: application/json' \
  -d @- <<EOF
{
  "feature_key": "${NEW_FEATURE}",
  "brief": "$(cat path/to/documents_2_brief.md | jq -Rs .)",
  "skip_po": false,
  "skip_gate": false
}
EOF
```

Capture the returned `run_id` and tail
`webapp/backend/logs/orchestrator/<ts>/run.log`.

---

## Post-launch verification (first 5 minutes)

| Check | Expected |
|---|---|
| Orchestrator phase `index_initial` completes | graphify + claude-context rebuild from clean state |
| PO `_brownfield/_codebase_context/CODEBASE_CONTEXT.md` written | references `$MAIN_REF` code only, no documents_1 surfaces |
| PO sprint plan BL count | sized to the new brief, not a copy of prior BL list |
| No `R11 no-op` short-circuits in early BLs | engineer is actually producing diffs |
| Gate PRE on first BL passes | confirms clean baseline |

If any of those drift, abort the run and re-audit Steps 1–9 — most
common miss is forgetting Step 4 (graphify cache) or Step 5 (Milvus
collection).

---

## Rollback

To return to the prior feature's working state:

```bash
# Restore .agentic-skills.json to point at agentic-skills-work
# Re-checkout the prior agent branch in target
# Graphify and Milvus will re-index on next call — no manual restore needed
```

The forked branch (`$NEW_AGENT_BRANCH`) can be left in place or deleted
once the operator confirms it's no longer needed.

---

## Open gaps (file as ledger entries if hit)

- **Milvus collection name discovery** is manual (Step 5). Should be a
  one-shot script. (Candidate ledger item.)
- **I-3 closure** would make Step 3 automatic at prior-run termination.
  Tracked in `ARCHITECT_PLAN.md` Batch B (`closure_check`).
- **Feature-key registry** doesn't exist; Step 9 is a grep. A real
  registry with `register / list / archive` operations would make
  collisions impossible.

---

*Created 2026-05-26. Worked example targets the `documents_2`
follow-on to `documents_1` on `full-stack-fastapi-template`. Update
when any of the keyed surfaces in the table at the top change.*
