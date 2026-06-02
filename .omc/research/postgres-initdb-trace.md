# postgres-initdb-trace.md
# Causal trace — podcast-postgres fails to start on fresh deployment
# Generated: 2026-05-27

---

## Observation

`podcast-postgres` exits with code 1 and restarts 13 times. The terminal log lines are:

```
initdb: error: directory "/var/lib/postgresql/data" exists but is not empty
initdb: detail: It contains a dot-prefixed/invisible file, perhaps due to it being a mount point.
initdb: hint: Using a mount point directly as the data directory is not recommended.
```

The container bind-mount is confirmed:
`docker inspect` → `/home/yoann/podcast/data/postgres:/var/lib/postgresql/data:rw`

---

## Evidence collected (primary artifacts)

| Artifact | Value |
|----------|-------|
| `stat data/postgres/` | UID=70 (UNKNOWN on host), GID=1000 (yoann), mode=0700 |
| `ls data/` | `data/postgres/` — owned UID 70, mode drwx------; host user cannot read it |
| `ls data/redis/` | owned `ollama` (not postgres UID), contains `.gitkeep` + `appendonlydir/` — redis is running |
| `git ls-files --cached data/` | Returns NOTHING — no `.gitkeep` files are committed to HEAD |
| `git ls-files --others data/` | `data/artifacts/.gitkeep`, `data/debug/.gitkeep`, `data/n8n/.gitkeep`, `data/redis/.gitkeep`, `data/session/.gitkeep` — all UNTRACKED |
| `git show HEAD:data/postgres/.gitkeep` | `fatal: … not in HEAD` — never committed |
| `data/postgres/` Modify timestamp | `2026-05-26 18:53:55` — same day as all other data/ subdirs (scaffolding day) |
| `data/postgres/` Access timestamp | `2026-05-27 13:45:26` — touched recently (container restart attempts) |

Key inference from timestamps: the directory was scaffolded on 2026-05-26 and has been accessed by postgres attempts since. Its Modify time has NOT changed from scaffold day, meaning no PG_VERSION or base/ directory was ever written — postgres has never successfully initialized.

---

## Hypothesis Table

| Rank | Hypothesis | Confidence | Evidence Strength | Why it remains plausible |
|------|-----------|------------|-------------------|--------------------------|
| 1 | **H1 — `.gitkeep` file blocks initdb** | **High** | Strong (direct artifact) | `.gitkeep` is a dot-prefixed file; initdb's own error message names "dot-prefixed/invisible file"; the file was placed there during scaffolding and is still present (dir unreadable but not empty by UID check) |
| 2 | **H4 — Container UID 70 chowned the dir, host user lost access** | High (co-cause) | Strong (stat output) | `stat` confirms UID=70, mode=0700 — this is a confirmed side-effect of postgres touching the dir, not the root cause of the init failure but is a confirmed operational fact |
| 3 | **H3 — Image init-script convention conflict** | Medium | Moderate | `postgres:16-alpine` docker-entrypoint.sh uses `ls -A $PGDATA`; if non-empty AND no PG_VERSION → calls initdb → initdb rejects dot files. This is the mechanism, not an independent cause |
| 4 | **H2 — Leftover state from a previous failed run** | Low | Weak | Dir Modify time unchanged from scaffold day; no evidence of partial PG data (PG_VERSION, base/) ever written; UID 70 chown happened without initdb completing |

---

## Evidence For Each Hypothesis

**H1:**
- `data/postgres/` mode=0700 owned UID=70 confirms postgres container touched it but did NOT complete initdb (no PG_VERSION written, Modify time = scaffold day)
- The `.gitkeep` file was present before first container start — confirmed by: (a) scaffold timestamp matches all other data/ dirs; (b) git ls-files --others shows `.gitkeep` files exist as untracked in all OTHER data subdirs (n8n, redis, artifacts, debug, session); (c) redis/data shows its `.gitkeep` still present even after redis ran successfully
- initdb error message text is literal: "dot-prefixed/invisible file" — `.gitkeep` is exactly that
- `postgres:16-alpine` docker-entrypoint.sh (public source): calls `ls -A "$PGDATA"` to test emptiness; `.gitkeep` (dot-prefixed) IS returned by `ls -A`, making the dir appear non-empty; then calls `initdb --pgdata="$PGDATA"` which independently checks and rejects the dot file

**H4 (confirmed co-effect, not root cause):**
- `stat data/postgres/` → Uid=70, mode=0700 is direct evidence
- This happened because postgres container started, the entrypoint ran `chown -R postgres:postgres "$PGDATA"` (standard in the alpine image) BEFORE calling initdb, then initdb failed
- This is a consequence of H1, not an independent cause

**H3 (mechanism, not independent cause):**
- The `postgres:16-alpine` entrypoint chain is: chown → test non-empty → if non-empty AND no PG_VERSION → run initdb → initdb rejects dot files
- This explains WHY `.gitkeep` causes failure (the image invokes initdb which has this guard), but the root cause is still the file's presence

**H2:**
- No evidence of partial PG state: Modify time of the dir equals scaffold creation time (no writes after that)
- If a prior run had progressed past chown to actual initdb writes, Modify time would differ
- Down-ranked: requires assuming prior partial run that left only dotfiles — not supported by timestamps

---

## Evidence Against / Gaps

**H1:**
- We cannot directly `ls` inside `data/postgres/` (permission denied) to confirm `.gitkeep` is still present there — this is the only gap
- However: (a) redis dir still has its `.gitkeep` after redis ran, confirming the scaffold pattern persists; (b) git ls-files --others shows `.gitkeep` files exist in every OTHER data/ subdir; (c) the initdb error message text is specific enough to be nearly conclusive

**H4:**
- Not a root cause; it is the effect of the entrypoint running chown before initdb. Confirmed by stat output.

**H3:**
- Not independent: it only fires because `.gitkeep` is present. Remove `.gitkeep` → H3 mechanism never triggers.

**H2:**
- Directly contradicted by Modify timestamp evidence (Tier 2 artifact). Down-ranked.

---

## Rebuttal Round

**Best challenge to H1 (current leader):**
"Perhaps `data/postgres/.gitkeep` was never actually created — the `.gitignore` pattern `!data/**/.gitkeep` might have prevented git from creating it, and the directory was born empty. The chown by UID 70 is enough to explain the permission-denied; maybe an OS-level `.` or `..` dotfile triggered initdb."

**Why H1 still stands:**
- `ls -A` in bash does NOT show `.` or `..` — those are excluded by `-A` (almost-all). initdb's own message says "dot-prefixed/invisible file", meaning it found a real file beyond `.` and `..`.
- Every other data/ subdir (n8n, redis, artifacts, debug, session) shows its `.gitkeep` present as an untracked file in git ls-files --others. The scaffold script created `.gitkeep` in all data subdirs uniformly. There is no evidence `data/postgres/` was treated differently during scaffolding.
- Redis dir (`data/redis/`) has its `.gitkeep` present AND redis started fine — confirming `.gitkeep` files were laid down in the data dirs before first container start.
- The only reason we cannot directly confirm `data/postgres/.gitkeep` is the UID=70 mode=0700 lock-out, itself caused by the failed first start.

---

## Convergence / Separation Notes

H1 and H3 converge to the same root cause: `.gitkeep` present → initdb sees non-empty non-initialized dir → fails. H3 is the mechanism through which H1 causes the failure; they are not independent.

H4 is a confirmed secondary effect (chown by postgres entrypoint before initdb ran), not a competing root cause.

H2 is contradicted by timestamp evidence and eliminated.

The causal chain is linear: one root cause, one mechanism, one side-effect.

---

## Causal Chain

```
Phase 0 scaffolding
  └─ `data/postgres/` created with `data/postgres/.gitkeep` (empty 0-byte file)
        │
        │  (git tracks .gitkeep in other dirs; .gitignore exception !data/**/.gitkeep
        │   was declared but files were never `git add`-ed → all .gitkeep files remain
        │   untracked; this does NOT affect their physical presence on disk)
        │
First `docker compose up`
  └─ postgres:16-alpine entrypoint starts
        └─ Step 1: `chown -R postgres:postgres /var/lib/postgresql/data`
             → UID 70 takes ownership, mode 0700
             → host user yoann loses read access (confirmed by permission denied)
        └─ Step 2: `[ "$(ls -A "$PGDATA")" ]` — is dir non-empty?
             → `ls -A` returns `.gitkeep` → TRUE → dir is non-empty
        └─ Step 3: check for PG_VERSION → absent → not already initialized
        └─ Step 4: call `initdb --pgdata=/var/lib/postgresql/data`
             → initdb scans dir, finds `.gitkeep` (dot-prefixed file)
             → FATAL: "directory exists but is not empty"
             → "It contains a dot-prefixed/invisible file"
        └─ Container exits code 1
             → restart_count increments
             → Loop: chown already done; .gitkeep still there; same failure every restart
```

**Why this is the FIRST time it surfaces:** fresh deployment, `data/postgres/` has never been initialized. On an already-initialized host the dir would contain PG_VERSION, base/, etc. — the entrypoint skips initdb entirely for an initialized dir.

**Why redis works but postgres doesn't:** redis-server does NOT call any equivalent of initdb. It starts, reads its data dir, and writes AOF files. A `.gitkeep` file in `data/redis/` is silently ignored by redis-server. Confirmed: `data/redis/` contains `.gitkeep` + `appendonlydir/` and redis is running.

---

## Current Best Explanation

Root cause: `data/postgres/.gitkeep` — a dot-prefixed placeholder file placed during scaffolding — is present in the bind-mounted directory when `postgres:16-alpine` first starts. The image's `docker-entrypoint.sh` calls `initdb` on a non-empty, non-initialized directory. `initdb` (PostgreSQL's own tool, independent of the Docker wrapper) rejects any directory that is non-empty but lacks `PG_VERSION`, and explicitly errors on dot-prefixed files. The container exits 1 on every restart attempt because the file is never removed and initdb never completes.

Confidence: HIGH. The only gap is inability to directly `ls` inside `data/postgres/` due to the mode=0700 UID=70 lock-out (itself caused by the first failed start). All circumstantial evidence converges: scaffolding pattern, redis parallel, git ls-files --others output, initdb error text.

---

## Critical Unknown

Whether `data/postgres/.gitkeep` is still physically present inside the directory (we cannot confirm directly due to UID=70 mode=0700 ownership). If UID 70 deleted it during a restart attempt, a different cause exists. However, there is no mechanism in the postgres entrypoint that deletes files from PGDATA — it only chowns and then calls initdb, which exits on the first found dot file without deleting anything.

---

## Discriminating Probe

```bash
sudo ls -la /home/yoann/podcast/data/postgres/
```

This single command collapses all remaining uncertainty: if `.gitkeep` is present (expected), H1 is confirmed with certainty. If the dir is empty, a different cause must be sought.

If `sudo` is unavailable:
```bash
docker run --rm -v /home/yoann/podcast/data/postgres:/pgdata alpine ls -la /pgdata/
```
A read-only alpine container can traverse UID=70 dirs because Docker bind-mounts bypass host-user permission checks.

---

## Fix Proposal

**Immediate fix (one-time, before first `docker compose up`):**

```bash
# Remove the gitkeep from the postgres data dir only — postgres manages this dir exclusively
rm /home/yoann/podcast/data/postgres/.gitkeep
# Or if already chowned to UID 70:
docker run --rm -v /home/yoann/podcast/data/postgres:/pgdata alpine rm /pgdata/.gitkeep
```

**Structural fix (prevent recurrence on any fresh clone):**

In `.gitignore`, add a postgres-specific exclusion so `.gitkeep` is never placed there:

```
# data/postgres is managed entirely by the postgres container — no placeholder needed
data/postgres/
```

Or, more surgically, document in `docker-compose.yml` that `data/postgres/` must be empty before first start (add a comment on the volume line).

The `.gitkeep` pattern is correct for `data/redis/`, `data/n8n/`, `data/artifacts/`, `data/debug/`, `data/session/` — only `data/postgres/` is incompatible with it because `initdb` enforces strict emptiness.
