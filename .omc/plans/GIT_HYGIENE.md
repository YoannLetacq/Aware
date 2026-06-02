# GIT_HYGIENE.md — Git Hygiene Plan for `podcast` Repo

> DRAFT — executors: do NOT create repo-root files until main-agent approves.
> Citations: `refs/veille_auto/.gitignore:LINE` = `.omc/refs/veille_auto/.gitignore`.

---

## 1. Proposed `.gitignore`

```gitignore
# ==========================================
# GITIGNORE - n8n Podcast Pipeline
# ==========================================

# Secrets & credentials (refs/veille_auto/.gitignore:3-11)
.env
.env.*
!.env.example
!.env.template
*.pem
*.key
*.crt
.db_password
.n8n_password
.n8n_encryption_key

# H4: storageState.json = bearer credential — ignore aggressively
storageState.json
*storage-state*.json
playwright-storage-state.json

# Persistent data volumes (refs/veille_auto/.gitignore:14-20)
data/
backups/*.sql
backups/*.tar.gz
backups/*.bak
artifacts/
runs/

# Logs (refs/veille_auto/.gitignore:19-20)
**/logs
logs/*.log
!logs/.gitkeep

# Docker (refs/veille_auto/.gitignore:23-24)
.docker/
docker-compose.override.yml

# Playwright / browser automation — incl. M4 failure captures
.playwright/
playwright-report/
test-results/
screenshots/
traces/
*.har
*.zip

# Node (refs/veille_auto/.gitignore:43-45)
node_modules/
npm-debug.log
yarn-error.log
.pnpm-debug.log

# Python worker (refs/veille_auto/.gitignore:47-52)
__pycache__/
*.py[cod]
*$py.class
.Python
venv/
.venv/
env/
.pytest_cache/
.ruff_cache/
.mypy_cache/

# OS junk (refs/veille_auto/.gitignore:27-30)
.DS_Store
Thumbs.db
*.swp
*.swo
*~

# IDE — negation keeps .vscode/extensions.json (refs/veille_auto/.gitignore:31)
.vscode/*
!.vscode/extensions.json
.idea/

# Temporaries (refs/veille_auto/.gitignore:33-37)
tmp/
temp/
*.tmp
*.bak

# OMC runtime state — refs/, plans/, research/ stay tracked
# (refs/veille_auto/.gitignore:67 ignores all .omc/; deliberate divergence)
.omc/state/
.omc/logs/
.omc/notepad.md
.omc/project-memory.json
.omc/artifacts/
.omc/reviews/

# Misc (refs/veille_auto/.gitignore:59-63)
DEPLOIEMENT.md
QUICKSTART.md
REVIEW.md
old.json
!data/.gitkeep
!backups/.gitkeep
```

---

## 2. Proposed `.gitattributes`

```gitattributes
# Normalize all text to LF on commit
* text=auto eol=lf

# Workflow JSON — text so n8n exports diff cleanly
*.json        text eol=lf
workflows/*.json text eol=lf

# SQL, shell, Docker
*.sql         text eol=lf
*.sh          text eol=lf
Dockerfile    text eol=lf
docker-compose*.yml text eol=lf

# Binary lock — audio/video/archives
*.mp3 binary
*.mp4 binary
*.wav binary
*.bin binary
*.zip binary
*.tar.gz binary
*.png binary
*.jpg binary
*.jpeg binary
```

---

## 3. Conventional Commits

### Type list

| Type | When to use |
|------|-------------|
| `feat` | New user-visible capability (new Discord command, new pipeline stage) |
| `fix` | Bug fix in existing behavior |
| `chore` | Dependency bumps, tooling, generated files, no behavior change |
| `docs` | Documentation only (README, conduct files, plan files) |
| `ci` | CI pipeline changes (GitHub Actions, linting config) |
| `infra` | Docker Compose, volume config, Postgres schema, secret management |
| `workflow` | n8n workflow JSON imports/exports — distinct change class from code |

`workflow` is a type (not a scope): n8n workflow JSON files are the primary
executable artifact — analogous to migrations, needing their own blame lane.

### Scopes: `bot` · `n8n` · `worker` · `db` · `compose` · `scripts`

### Five example subjects

```
feat(bot): add /podcast slash command with subject + style args
infra(compose): extract worker service and wire Postgres LISTEN/NOTIFY queue
workflow(n8n): import dispatcher workflow with job_id handoff node
fix(worker): handle storageState expiry with re-auth fallback path
chore(db): add job_state table with (user_id, subject_hash) idempotency key
```

---

## 4. Branch Model

| Branch | Pattern | Notes |
|--------|---------|-------|
| Default | `master` | Protected; no direct pushes |
| Feature | `feat/<slug>` | e.g. `feat/discord-slash-command` |
| Fix | `fix/<slug>` | Single-concern bug fixes |
| Infra | `infra/<slug>` | Compose, DB, secret changes |

All changes land via PR; squash-and-merge for features, rebase for single-commit fixes.

**Remote-side protection** (GitHub — user configures after `git remote add`):
enforce "Require PR + 1 approval", "Require status checks", "Block force pushes".
Pre-push hooks warn locally but GitHub branch protection is the authoritative layer.

---

## 5. Pre-commit Hook Plan

**Do NOT install yet** — wire once the repo has real content to lint.
Uses the [`pre-commit`](https://pre-commit.com/) framework.

Hooks: `gitleaks` (secret scan), `yamllint` (compose files), `check-json`
(n8n workflow JSON), `hadolint` (Dockerfile), `end-of-file-fixer`,
`trailing-whitespace`, `check-added-large-files` (>500 KB), `detect-private-key`.

### Sample `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-json
      - id: check-yaml
        args: [--unsafe]
      - id: check-added-large-files
        args: [--maxkb=500]
      - id: detect-private-key

  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.4
    hooks:
      - id: gitleaks

  - repo: https://github.com/adrienverge/yamllint
    rev: v1.35.1
    hooks:
      - id: yamllint
        files: docker-compose.*\.yml$
        args: [-d, relaxed]

  - repo: https://github.com/hadolint/hadolint
    rev: v2.12.0
    hooks:
      - id: hadolint-docker
        files: Dockerfile.*
```

> Install: `pip install pre-commit && pre-commit install && pre-commit run --all-files`
