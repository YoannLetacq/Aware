# SHARED_N8N_REFACTOR — Mutualisation de `veille-n8n` avec la stack podcast

> **Mission.** Supprimer le conteneur n8n de la stack podcast et faire de
> `veille-n8n` (déjà déployé par `veille_auto`) l'unique instance n8n
> qui héberge AUSSI le workflow podcast. Les deux stacks gardent leurs
> Postgres / Redis isolés. Communication via un réseau Docker externe
> partagé `podcast-bridge`.
>
> **Scope.** Diffs compose (deux dépôts), `.env` podcast, scripts,
> docs/n8n-setup.md, plan de migration, rollback, risques, branches.
> **Hors scope.** Modification fonctionnelle du workflow podcast,
> changement de version n8n, rotation de `N8N_ENCRYPTION_KEY`.

Sources citées (file:line) :
- Compose podcast `docker-compose.yml:6, 37, 64-120, 134, 137, 184, 186, 194, 234-236`
- Compose veille_auto `/home/yoann/veille_auto/docker-compose.yml:5, 35-93, 75, 201-203`
- `.env` podcast lignes `23, 25, 27, 29, 86`
- `bot/app/config.py:39` (`N8N_WEBHOOK_URL`)
- `worker/app/config.py:29` (`POSTGRES_HOST`)
- Scripts `scripts/start.sh:79-81,123-133`, `scripts/setup.sh:96-101`,
  `scripts/backup.sh:70-82`, `scripts/restore.sh:91`, `scripts/status.sh:59`,
  `scripts/logs.sh:11-13`
- Workflow `workflows/pipeline.json:51, 69` (credential placeholders)
- Docs `docs/n8n-setup.md:13, 41, 96-117, 252, 287-296`

---

## 0. Target topology

```
  ┌──────────────────────────────────────┐    ┌──────────────────────────────────────┐
  │ /home/yoann/veille_auto              │    │ /home/yoann/podcast                  │
  │  - veille-postgres                   │    │  - podcast-postgres                  │
  │  - veille-redis                      │    │  - podcast-redis                     │
  │  - veille-rsshub                     │    │  - podcast-bot                       │
  │  - veille-webdis                     │    │  - podcast-worker                    │
  │  - veille-n8n  ◄────── hosts BOTH workflows (veille + podcast)                   │
  │    networks: veille-network, podcast-bridge                                       │
  │                                                                                   │
  │           (shared external network: podcast-bridge)                               │
  │  podcast-postgres / podcast-redis / podcast-bot / podcast-worker on the bridge   │
  └──────────────────────────────────────┘    └──────────────────────────────────────┘
```

- ONE n8n container : `veille-n8n` (port 5678 inchangé).
- Le bot podcast POST sur `http://veille-n8n:5678/webhook/podcast` (DNS conteneur via `podcast-bridge`).
- Le workflow veille existant reste sur son URL `localhost:5678` côté UI, INCHANGÉ.

---

## 1. Pre-flight checks (opérateur, BEFORE any change)

```bash
# 1.1 veille_auto sain
cd /home/yoann/veille_auto
docker compose ps                                       # tous les services 'healthy' / 'running'
docker compose exec -T n8n wget -qO- http://localhost:5678/healthz   # 200

# 1.2 Inventaire conteneurs courants
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Networks}}\t{{.Status}}'

# 1.3 Sauvegarde du volume n8n veille_auto (state, credentials, workflows)
TS=$(date -u +%Y%m%d-%H%M%S)
sudo tar -czf "/home/yoann/veille_auto/backups/n8n-pre-merge-${TS}.tar.gz" \
  -C /home/yoann/veille_auto data/n8n

# 1.4 Dump Postgres veille_auto (sécurité)
docker compose -f /home/yoann/veille_auto/docker-compose.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip > "/home/yoann/veille_auto/backups/db-pre-merge-${TS}.sql.gz"

# 1.5 Capture du workflow podcast actuel s'il existait dans une instance précédente
# (ici : aucun, le workflow n'a jamais été importé puisque la stack n'a jamais tourné côté prod)

# 1.6 Snapshot config podcast (référence rollback)
cp /home/yoann/podcast/docker-compose.yml /home/yoann/podcast/docker-compose.yml.pre-merge.bak
cp /home/yoann/podcast/.env              /home/yoann/podcast/.env.pre-merge.bak
```

Bloquant : tout `docker ps` indiquant `veille-n8n` non `healthy` → STOP, fixer
veille_auto d'abord. Les artefacts `*.bak` servent au rollback §8.

---

## 2. Network creation

```bash
docker network create podcast-bridge \
  --driver bridge \
  --label purpose=shared-n8n-bridge \
  --label managed-by=manual
# (Pas de --subnet : on laisse Docker allouer pour éviter une collision RFC1918.)

# Vérifier
docker network inspect podcast-bridge --format '{{.Name}} {{.Driver}} {{.IPAM.Config}}'
```

Idempotent : si le réseau existe déjà, `docker network create` retourne une
erreur non fatale ; on l'ignore après vérification du label.

---

## 3. Diff `/home/yoann/veille_auto/docker-compose.yml`

> Cible : ajouter `podcast-bridge` (external), attacher `n8n` aux deux réseaux,
> étendre le whitelist `N8N_ENV_VARS`, exposer les nouvelles variables.

### 3.1 Top-level `networks:` (lignes 201-203)

**Avant** :
```yaml
networks:
  veille-network:
    driver: bridge
```

**Après** :
```yaml
networks:
  veille-network:
    driver: bridge
  podcast-bridge:
    external: true
    name: podcast-bridge
```

### 3.2 Service `n8n` (lignes 35-93)

**a. Bloc `environment` (après ligne 73 `- N8N_API_KEY=...`)** — ajouter :
```yaml
      # Podcast pipeline integration (shared n8n)
      - WORKER_SHARED_TOKEN=${WORKER_SHARED_TOKEN}
      - KILL_SWITCH=${KILL_SWITCH:-0}
      - RATE_LIMIT_PER_USER_DAY=${RATE_LIMIT_PER_USER_DAY:-3}
      - RATE_LIMIT_GLOBAL_DAY=${RATE_LIMIT_GLOBAL_DAY:-20}
      - OPERATOR_DISCORD_WEBHOOK=${OPERATOR_DISCORD_WEBHOOK}
```

**b. `N8N_ENV_VARS` (ligne 75)** — étendre la whitelist :

**Avant** :
```yaml
      - N8N_ENV_VARS=DISCORD_WEBHOOK_URL,DISCORD_WEBHOOK_TECH_NEWS,DISCORD_WEBHOOK_COMPANIES,DISCORD_WEBHOOK_REDDIT,DISCORD_WEBHOOK_OTHERS,DISCORD_BOT_TOKEN,DISCORD_ALLOWED_AUTHORS,GEMINI_API_KEY,GEMINI_MODEL,POSTGRES_USER,POSTGRES_PASSWORD,POSTGRES_DB,WEBHOOK_URL,N8N_API_KEY
```

**Après** :
```yaml
      - N8N_ENV_VARS=DISCORD_WEBHOOK_URL,DISCORD_WEBHOOK_TECH_NEWS,DISCORD_WEBHOOK_COMPANIES,DISCORD_WEBHOOK_REDDIT,DISCORD_WEBHOOK_OTHERS,DISCORD_BOT_TOKEN,DISCORD_ALLOWED_AUTHORS,GEMINI_API_KEY,GEMINI_MODEL,POSTGRES_USER,POSTGRES_PASSWORD,POSTGRES_DB,WEBHOOK_URL,N8N_API_KEY,WORKER_SHARED_TOKEN,KILL_SWITCH,RATE_LIMIT_PER_USER_DAY,RATE_LIMIT_GLOBAL_DAY,OPERATOR_DISCORD_WEBHOOK
```

**c. Bloc `networks:` du service n8n (ligne 92-93)** :

**Avant** :
```yaml
    networks:
      - veille-network
```

**Après** :
```yaml
    networks:
      - veille-network
      - podcast-bridge
```

### 3.3 `.env` côté veille_auto

`veille_auto/.env` n'a actuellement AUCUNE des cinq variables podcast.
Source de vérité unique recommandée : symlink (option A) ou bloc dupliqué
manuel (option B). Voir §9 risque R5.

**Option A — symlink (recommandé, simple)** :
```bash
# Crée /home/yoann/veille_auto/.env.podcast pointant vers la SOT podcast,
# puis docker-compose lit env_file en plus de .env.
ln -s /home/yoann/podcast/.env /home/yoann/veille_auto/.env.podcast
```
Puis ajouter au service `n8n` du compose veille_auto :
```yaml
    env_file:
      - .env.podcast
```
(Cette ligne n'existe pas aujourd'hui ; à ajouter sous `environment:` à la
ligne 39.)

**Option B — bloc dupliqué dans `veille_auto/.env`** : copier-coller les 5
variables (`WORKER_SHARED_TOKEN`, `KILL_SWITCH`, `RATE_LIMIT_PER_USER_DAY`,
`RATE_LIMIT_GLOBAL_DAY`, `OPERATOR_DISCORD_WEBHOOK`) depuis `podcast/.env`
lignes 84-96 vers `veille_auto/.env`. Risque : drift entre les deux fichiers.

---

## 4. Diff `/home/yoann/podcast/docker-compose.yml`

### 4.1 Suppression du service `n8n` (lignes 59-120)

Supprimer intégralement le bloc `n8n:` depuis le commentaire ligne 59
`# N8N - Trigger ingestion + Discord post-back` jusqu'à ligne 120 incluse
(dernier `- podcast-network`).

### 4.2 Rename `postgres` → `podcast-postgres` (lignes 6-31)

**Avant (ligne 6 et 8)** :
```yaml
  postgres:
    image: postgres:16-alpine
    container_name: podcast-postgres
```

**Après** :
```yaml
  podcast-postgres:
    image: postgres:16-alpine
    container_name: podcast-postgres
```

Le `container_name` était déjà `podcast-postgres` ligne 8 → aucun changement
d'identité runtime ; seule la clé de service change pour éviter la collision
si jamais les deux composes sont fusionnés dans un même `docker compose`.

### 4.3 Rename `redis` → `podcast-redis` (lignes 37-57)

**Avant (ligne 37, 39)** :
```yaml
  redis:
    image: redis:7-alpine
    container_name: podcast-redis
```

**Après** :
```yaml
  podcast-redis:
    image: redis:7-alpine
    container_name: podcast-redis
```

### 4.4 Top-level `networks:` (lignes 234-236)

**Avant** :
```yaml
networks:
  podcast-network:
    driver: bridge
```

**Après** :
```yaml
networks:
  podcast-network:
    driver: bridge
  podcast-bridge:
    external: true
    name: podcast-bridge
```

### 4.5 `networks:` par service (4 services restants)

Ajouter `- podcast-bridge` à la liste `networks:` de chaque service :
- `podcast-postgres` ligne 30-31
- `podcast-redis` ligne 56-57
- `worker` ligne 167-168
- `bot` ligne 201-202

**Exemple pour `bot`** :

**Avant** :
```yaml
    networks:
      - podcast-network
```

**Après** :
```yaml
    networks:
      - podcast-network
      - podcast-bridge
```

(Identique pour les 3 autres services.)

### 4.6 `depends_on` de `bot` (lignes 193-195)

**Avant** :
```yaml
    depends_on:
      n8n:
        condition: service_healthy
```

**Après** :
```yaml
    # n8n is hosted by the veille_auto stack (container: veille-n8n).
    # Start veille_auto first ; bot retries the webhook with its own backoff.
    depends_on:
      podcast-postgres:
        condition: service_healthy
```

(`bot` n'avait pas de dépendance Postgres mais en a besoin pour idempotency
lookup phase 5 ; ajout cohérent et non bloquant.)

### 4.7 `depends_on` de `worker` (lignes 157-161)

**Avant** :
```yaml
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
```

**Après** :
```yaml
    depends_on:
      podcast-postgres:
        condition: service_healthy
      podcast-redis:
        condition: service_healthy
```

### 4.8 Variables `*_HOST` dans les `environment` du worker (lignes 134-137)

**Avant** :
```yaml
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - REDIS_HOST=redis
      - REDIS_PORT=6379
```

**Après** :
```yaml
      - POSTGRES_HOST=podcast-postgres
      - POSTGRES_PORT=5432
      - REDIS_HOST=podcast-redis
      - REDIS_PORT=6379
```

### 4.9 `N8N_WEBHOOK_URL` & `WEBHOOK_URL` du bot (lignes 184, 186)

**Avant** :
```yaml
      - WEBHOOK_URL=${WEBHOOK_URL:-http://n8n:5678/}
      - WORKER_SHARED_TOKEN=${WORKER_SHARED_TOKEN}
      - N8N_WEBHOOK_URL=${N8N_WEBHOOK_URL:-http://n8n:5678/webhook/podcast}
```

**Après** :
```yaml
      - WEBHOOK_URL=${WEBHOOK_URL:-http://veille-n8n:5678/}
      - WORKER_SHARED_TOKEN=${WORKER_SHARED_TOKEN}
      - N8N_WEBHOOK_URL=${N8N_WEBHOOK_URL:-http://veille-n8n:5678/webhook/podcast}
```

---

## 5. Diff `/home/yoann/podcast/.env`

Référence : lignes 22-29, 80-86.

```diff
@@ N8N section (lines 21-29) @@
 # ==========================================
-# N8N
+# N8N — hosted by the veille_auto stack (container: veille-n8n)
+# These variables are no longer consumed by the podcast compose because
+# the podcast stack does not run its own n8n. They are kept commented for
+# reference / rollback only ; veille_auto owns the n8n instance lifecycle.
 # ==========================================
-# Generate with: openssl rand -hex 32
-N8N_ENCRYPTION_KEY=828759c3...   # owned by veille_auto/.env now
-# Generate with: openssl rand -hex 24
-N8N_API_KEY=eyJhbGciOiJIUzI1NiIs...   # owned by veille_auto/.env now
-# Host-side port
-N8N_PORT=5679
-# Public webhook base URL (used by n8n for self-referencing webhooks)
-WEBHOOK_URL=http://localhost:5679/
+# N8N_ENCRYPTION_KEY  — see veille_auto/.env (line 19)
+# N8N_API_KEY         — see veille_auto/.env (line 26)
+# N8N_PORT            — irrelevant; veille_auto exposes 5678 on the host
+WEBHOOK_URL=http://localhost:5678/

@@ Internal Security (lines 80-86) @@
 WORKER_SHARED_TOKEN=7f9b9547...
-# n8n webhook URL for the bot to POST trigger payloads to
-N8N_WEBHOOK_URL=http://n8n:5678/webhook/podcast
+# n8n webhook URL for the bot to POST trigger payloads to.
+# Container DNS via the shared `podcast-bridge` network.
+N8N_WEBHOOK_URL=http://veille-n8n:5678/webhook/podcast
```

Postgres / Redis / Discord / Gemini : INCHANGÉS.

---

## 6. Service-hostname references — files to update

| File | Line(s) | Change |
|------|---------|--------|
| `bot/app/config.py` | 39 | aucun (lit `_required("N8N_WEBHOOK_URL")`, valeur fournie via compose §4.9 / `.env` §5) |
| `worker/app/config.py` | 29, 36 | aucun (lit `_required("POSTGRES_HOST")` / `REDIS_HOST`, valeurs fournies via compose §4.8) |
| `docker-compose.yml` | 134, 137, 184, 186 | déjà couvert §4.8 / §4.9 |
| `scripts/start.sh` | 79-81, 123-133 | remplacer `postgres`/`redis`/`n8n` par `podcast-postgres`/`podcast-redis` ; supprimer la sonde `n8n`/`N8N_PORT` ; supprimer ligne 131 `n8n: http://localhost:${N8N_PORT}/` ; ajouter note "n8n hosted by veille_auto" |
| `scripts/setup.sh` | 96-101 | supprimer `data/n8n` (mkdir et chmod) — plus de volume n8n local |
| `scripts/backup.sh` | 70-82 | s/`docker compose exec -T postgres`/`docker compose exec -T podcast-postgres`/ ; supprimer la section archivage `data/n8n` (ligne 78-82) — n8n est sauvegardé par veille_auto |
| `scripts/restore.sh` | 89-99 | s/`docker compose exec -T postgres`/`docker compose exec -T podcast-postgres`/ ; supprimer la branche `n8n-*.tar.gz` (les n8n backups sont du ressort veille_auto) |
| `scripts/status.sh` | 56-65 | s/`docker compose exec -T postgres`/`docker compose exec -T podcast-postgres`/ |
| `scripts/logs.sh` | 11-13 | mettre à jour les exemples : `./scripts/logs.sh podcast-postgres`, retirer `n8n` |
| `scripts/seed-google-session.sh` | — | aucun (n'utilise pas n8n) |
| `workflows/pipeline.json` | 51, 69 | aucun changement de fichier (les ID `REPLACE_AT_IMPORT_POSTGRES`/`REDIS` sont remplacés à l'import dans la nouvelle UI). En revanche **les credentials créés dans `veille-n8n` doivent pointer Host=`podcast-postgres` / `podcast-redis`** — couvert par la nouvelle version de `docs/n8n-setup.md` (§4 ci-dessous). |
| `db/init.sql` | — | aucune référence de hostname → aucun changement |
| `docs/n8n-setup.md` | §1 (lignes 8-36), §2 (39-52), §4 (88-119), §5 (162-180), §7 (244-268), §8 (281-300) | réécriture majeure ; voir §6.1 ci-dessous |

### 6.1 Réécriture `docs/n8n-setup.md` (résumé des sections impactées)

- **§1 Prérequis** : retirer la consigne "vérifier que `n8n` est `healthy`
  via `docker compose ps`" depuis le compose podcast. Remplacer par : "le
  conteneur `veille-n8n` doit être `healthy`, vérifier via
  `docker compose -f /home/yoann/veille_auto/docker-compose.yml ps`".
- **§2 Premier accès n8n** : l'URL reste `http://localhost:5678/` (port
  veille_auto). Le compte propriétaire EXISTE DÉJÀ (créé lors de l'install
  veille_auto). **Ne pas re-créer.**
- **§4 Créer les credentials** :
  - **Postgres** : Host = `podcast-postgres` (au lieu de `postgres`),
    Port = `5432`, le reste inchangé. Le nom du credential est libre,
    suggérer "Podcast Postgres" pour le distinguer du credential
    "Veille Postgres" existant.
  - **Redis** : Host = `podcast-redis`, Port = `6379`, DB = `0`.
  - **Discord Bot Token** & **Gemini API Key** : pré-existants côté
    `veille-n8n` (même bot, même clé Gemini). Réutiliser tels quels SI
    les valeurs sont identiques aux `.env` podcast. Sinon créer "Podcast
    Discord Bot" / "Podcast Gemini".
- **§5 Importer le workflow** : sélectionner les credentials "Podcast
  Postgres" / "Podcast Redis" sur les nœuds correspondants.
- **§7 Webhook entrant** : URL `http://localhost:5678/webhook/podcast`
  (port veille_auto, inchangé).
- **§8 Smoke test** : remplacer
  `docker compose exec postgres psql ...` par
  `docker compose exec podcast-postgres psql ...`. Idem pour Redis :
  `docker compose exec podcast-redis redis-cli LLEN podcast:jobs`.
- **§9 Dépannage** : ajouter une ligne :
  `veille-n8n ne résout pas podcast-postgres` → vérifier que le service
  est bien attaché à `podcast-bridge` (`docker inspect veille-n8n |
  grep -A2 podcast-bridge`).

---

## 7. Migration runbook (séquence stricte)

> Toutes les commandes sont à exécuter en tant que l'utilisateur `yoann`,
> depuis `/home/yoann`. Chaque étape produit une **assertion de succès**
> qui DOIT passer avant l'étape suivante. Échec à toute étape → §8 rollback.

### 7.1 — Stop podcast stack

```bash
cd /home/yoann/podcast
docker compose down                       # ne pas passer --volumes
docker volume ls | grep podcast-          # devrait être vide ou retourner uniquement les bind-mounts ./data/*
```

Volumes bind-mountés (`./data/postgres`, `./data/redis`, `./data/session`,
`./data/artifacts`, `./data/debug`) **conservés** : ce sont des bind mounts,
`down` ne les touche pas. `data/n8n` peut rester sur disque (purge optionnelle
après validation §7.7).

**Assertion** : `docker ps | grep podcast-` retourne 0 ligne.

### 7.2 — Create network

Exécuter le bloc §2 ci-dessus.

**Assertion** : `docker network inspect podcast-bridge --format '{{.Name}}'`
retourne `podcast-bridge`.

### 7.3 — Apply veille_auto compose diff (§3)

```bash
cd /home/yoann/veille_auto
git checkout -b feat/shared-n8n-bridge
# Appliquer les diffs §3.1, §3.2 (a, b, c)
# Appliquer §3.3 option A (symlink) OU B (duplication .env)
docker compose config                     # valide le YAML
```

**Assertion** : `docker compose config` retourne 0, l'output contient bien
`podcast-bridge` dans `networks.n8n.networks`.

### 7.4 — Recreate n8n on dual networks

```bash
cd /home/yoann/veille_auto
docker compose up -d --no-deps n8n        # recréation du seul n8n
sleep 10
docker compose ps n8n                     # status: healthy

# Vérifier le multi-network attachment
docker inspect veille-n8n --format '{{json .NetworkSettings.Networks}}' | jq 'keys'
# Attendu : ["podcast-bridge", "veille-network"]

# Vérifier que les nouvelles env vars sont chargées
docker compose exec n8n env | grep -E '^(WORKER_SHARED_TOKEN|KILL_SWITCH|RATE_LIMIT_PER_USER_DAY|RATE_LIMIT_GLOBAL_DAY|OPERATOR_DISCORD_WEBHOOK)='
# Attendu : 5 lignes, chacune avec une valeur non vide
```

**Assertion critique** : le workflow veille_auto existant FONCTIONNE
ENCORE. Ouvrir `http://localhost:5678/`, lancer manuellement le workflow
veille principal → résultat attendu identique au pré-merge. Si KO → §8.1.

### 7.5 — Apply podcast compose diff + .env diff (§4, §5, §6)

```bash
cd /home/yoann/podcast
git checkout -b feat/shared-n8n-bridge
# Appliquer §4 (compose), §5 (.env), §6 (scripts/, docs/n8n-setup.md)
docker compose config                     # valide le YAML
```

**Assertion** : `docker compose config` valide ; `grep -c "n8n:" docker-compose.yml`
retourne 0 (le service n8n est bien supprimé).

### 7.6 — Start podcast stack (4 services)

```bash
cd /home/yoann/podcast
docker compose up -d
sleep 15
docker compose ps                         # 4 lignes (pas 5) : podcast-postgres, podcast-redis, bot, worker
```

**Assertion** :
- `docker compose ps` montre exactement 4 services, tous `healthy` ou
  `running` (bot/worker n'ont pas tous un healthcheck).
- Depuis `veille-n8n`, la résolution DNS marche dans les deux sens :
  ```bash
  docker exec veille-n8n getent hosts podcast-postgres   # → IP du conteneur
  docker exec veille-n8n getent hosts podcast-redis      # → IP du conteneur
  docker exec podcast-bot getent hosts veille-n8n        # → IP du conteneur
  ```

### 7.7 — Import + configure podcast workflow in veille-n8n UI

1. Ouvrir `http://localhost:5678/`.
2. **Settings → Credentials → New** :
   - "Podcast Postgres" : Host `podcast-postgres`, Port `5432`,
     DB / User / Password depuis `podcast/.env`.
   - "Podcast Redis" : Host `podcast-redis`, Port `6379`, DB `0`.
   - "Podcast Webhook Auth" (Header Auth) : Header `Authorization`,
     valeur `Bearer {{ $env.WORKER_SHARED_TOKEN }}`.
3. **Workflows → Import from File** :
   `/home/yoann/podcast/workflows/pipeline.json`.
4. Lier les 3 nœuds (Webhook / Postgres / Redis) aux credentials créés.
5. **Activate** (toggle haut-droit). Vérifier que le webhook URL affiché
   est `http://localhost:5678/webhook/podcast`.

**Assertion** : un `curl -X POST -H "Authorization: Bearer $WORKER_SHARED_TOKEN"
-H "Content-Type: application/json" http://localhost:5678/webhook/podcast
-d '{...payload valide...}'` retourne 202 et insère une ligne dans
`podcast.jobs`.

### 7.8 — Register Discord slash command

Inchangé par rapport à `docs/n8n-setup.md §6` (commande `curl ... discord.com/api/v10/...`).

### 7.9 — Smoke test end-to-end

```bash
# Dans Discord :
/podcast subject:"Test mutualisation n8n veille_auto podcast" mode:podcast

# Vérifier côté podcast
docker compose -f /home/yoann/podcast/docker-compose.yml exec -T podcast-postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT id,status,subject FROM podcast.jobs ORDER BY created_at DESC LIMIT 1;"
docker compose -f /home/yoann/podcast/docker-compose.yml exec -T podcast-redis \
  redis-cli LLEN podcast:jobs
```

**Assertion finale** : 1 ligne `status=queued`, LLEN ≥ 1, veille_auto
workflow toujours fonctionnel.

### 7.10 — (Optionnel) Purge `data/n8n` côté podcast

Une fois §7.9 validé sur 24 h, supprimer le résidu `data/n8n/` côté
podcast :
```bash
sudo rm -rf /home/yoann/podcast/data/n8n
```

---

## 8. Rollback procedure

### 8.1 — Échec à §7.4 (veille_auto cassé après attach)

```bash
cd /home/yoann/veille_auto
git checkout -- docker-compose.yml        # restaure le compose pré-merge
# Si option A symlink : ne PAS retirer .env.podcast (inoffensif), mais
# retirer la ligne env_file ajoutée. Restauré par le checkout ci-dessus.
docker compose up -d --no-deps n8n        # recréation single-network
docker compose ps n8n                     # healthy
docker network rm podcast-bridge          # si plus aucun conteneur ne l'utilise
```

Workflow veille_auto vérifié manuellement à nouveau → si OK, retour à
l'état pré-§7.3. Investiguer la cause (le plus probable : N8N_ENV_VARS
mal-formaté, virgule manquante).

### 8.2 — Échec à §7.6 (podcast stack KO)

```bash
cd /home/yoann/podcast
docker compose down
cp docker-compose.yml.pre-merge.bak docker-compose.yml
cp .env.pre-merge.bak .env
git checkout -- scripts/ docs/n8n-setup.md
docker compose up -d                      # 5 services dont n8n local
```

Note : à ce stade veille-n8n est encore attaché à `podcast-bridge` (état
post-§7.4) — c'est bénin, l'interface est simplement inutilisée. La
retirer plus tard via §8.1.

### 8.3 — Échec à §7.7-9 (workflow podcast ne fonctionne pas dans veille-n8n)

Pas de désastre : la stack podcast tourne sans n8n local mais le webhook
échoue. Deux options :
- Fixer les credentials/import dans `veille-n8n` (le plus probable :
  Host=`postgres` au lieu de `podcast-postgres`).
- Si urgence : appliquer §8.2 pour réintroduire le n8n local et
  pointer `N8N_WEBHOOK_URL` à nouveau sur `http://n8n:5678/webhook/podcast`.

---

## 9. Risks + mitigations

| ID | Risque | Sévérité | Mitigation |
|----|--------|----------|------------|
| R1 | Collision `container_name` entre les deux stacks (`postgres`, `redis`) | HIGH | Rename clés de service en `podcast-postgres` / `podcast-redis` (§4.2, §4.3). `container_name` déjà préfixé `podcast-` côté podcast (ligne 8, 39). Côté veille_auto : `veille-postgres` / `veille-redis` (lignes 7, 122). Aucune collision après diff. |
| R2 | Upgrade n8n veille_auto casse le workflow podcast | MEDIUM | Tradeoff accepté (mission). Mitigation : épingler `n8nio/n8n:2.22.3` dans `veille_auto/docker-compose.yml:36` (actuellement `:latest`) — proposer en suivi mais hors scope ici. |
| R3 | Blast radius des credentials n8n élargie (un seul `N8N_ENCRYPTION_KEY` chiffre désormais les secrets podcast + veille) | MEDIUM | Surface explicite ; rotation `N8N_ENCRYPTION_KEY` post-merge nécessiterait de re-saisir tous les credentials. Marqué follow-up F-1, pas dans ce refactor. |
| R4 | `N8N_ENV_VARS` whitelist élargie expose `WORKER_SHARED_TOKEN` (et autres) aux Code nodes du workflow veille | MEDIUM | Les Code nodes veille n'ont aucune raison de lire ces vars ; risque = workflow malveillant importé par l'opérateur. Mitigation organisationnelle : revue des nouveaux workflows. Surface documentée dans §3.2.b. |
| R5 | Drift `.env` entre les deux dépôts pour les 5 nouvelles vars | MEDIUM | Option A symlink (§3.3) élimine le risque. Option B : ajouter une note dans `podcast/CLAUDE.md` "section Secret Rules" pour rappeler la duplication. |
| R6 | `WORKER_SHARED_TOKEN` divergent entre `veille-n8n` et `podcast-bot` (le bot envoie un Bearer que n8n ne reconnaît pas) | HIGH | Option A symlink rend la valeur identique par construction. Smoke test §7.9 détecterait le mismatch (n8n retournerait 401). |
| R7 | Le réseau `podcast-bridge` n'existe pas au moment où veille-n8n démarre → erreur "network not found" | LOW | Pre-flight §2 le crée AVANT §7.4. `external: true` impose son existence préalable. |
| R8 | Conflit de port 5678 si une autre stack écoute déjà | LOW | Inventaire §1.2 le détecte. Pas de changement de port. |
| R9 | Suppression du service n8n côté podcast efface `data/n8n` par accident | LOW | `docker compose down` (sans `-v`) ne touche pas les bind mounts. Purge manuelle dans §7.10, après validation 24 h. |
| R10 | Le workflow veille_auto utilise `WEBHOOK_URL=http://n8n:5678/` (ligne 50) — change-t-il avec l'ajout d'un network ? | LOW | Non : la valeur ENV reste, n8n résout `n8n` par son alias d'origine sur `veille-network`. Multi-attach n'altère pas l'alias `veille-network`. |

---

## 10. Branch + commit plan

**Deux dépôts, deux branches indépendantes**, fusionnées séparément.

### 10.1 — `/home/yoann/veille_auto` (branche `feat/shared-n8n-bridge`)

1. `chore(compose): declare podcast-bridge external network` — §3.1 uniquement.
2. `feat(n8n): attach veille-n8n to podcast-bridge for shared instance` — §3.2.c uniquement.
3. `feat(n8n): expose podcast pipeline env vars via N8N_ENV_VARS whitelist` — §3.2.a + §3.2.b.
4. `feat(env): source podcast secrets via env_file symlink` — §3.3 option A (env_file + symlink doc).

### 10.2 — `/home/yoann/podcast` (branche `feat/shared-n8n-bridge`)

1. `refactor(compose): rename postgres/redis services with podcast- prefix` — §4.2, §4.3, §4.7, §4.8.
2. `refactor(compose): remove embedded n8n service ; route bot to veille-n8n via shared bridge` — §4.1, §4.4, §4.5, §4.6, §4.9.
3. `chore(env): retire local n8n vars ; point N8N_WEBHOOK_URL to veille-n8n` — §5.
4. `chore(scripts): update hostnames + remove n8n-specific paths` — §6 lignes scripts/.
5. `docs(n8n-setup): rewrite for shared veille-n8n topology` — §6.1.

### 10.3 — Merge order

1. Merge veille_auto branch FIRST (state of `veille-n8n` capable of
   serving podcast must precede the podcast bot pointing at it).
2. Validate veille_auto workflow on master.
3. Merge podcast branch.
4. Smoke test §7.9 on master.
5. **Squash-merge** only after smoke test green (per AGENT_CONDUCT §1.6
   et CLAUDE.md `commit-convention`).

---

## 11. Acceptance checklist (operator sign-off)

- [ ] §1 pre-flight artefacts présents (`backups/n8n-pre-merge-*.tar.gz`,
      `backups/db-pre-merge-*.sql.gz`, `*.pre-merge.bak`).
- [ ] `podcast-bridge` network existe avec label `purpose=shared-n8n-bridge`.
- [ ] `veille_auto/docker-compose.yml` contient les 4 diffs §3.
- [ ] `veille-n8n` est attaché aux 2 réseaux ; les 5 nouvelles env vars sont
      visibles via `docker exec ... env | grep ...`.
- [ ] Workflow veille_auto historique → run manuel OK (régression checkpoint).
- [ ] `podcast/docker-compose.yml` ne contient PLUS de service `n8n`.
- [ ] Les services podcast-postgres / podcast-redis / bot / worker tournent ;
      DNS résout depuis veille-n8n vers podcast-postgres et inverse.
- [ ] Workflow podcast importé dans veille-n8n, credentials configurés sur
      Host=`podcast-postgres` / `podcast-redis`.
- [ ] Smoke test §7.9 produit `status=queued` dans `podcast.jobs`.
- [ ] Aucune valeur secrète n'a été dupliquée en clair ailleurs que dans
      `podcast/.env` (et le symlink option A).
- [ ] Doc `docs/n8n-setup.md` met à jour les sections §1, §2, §4, §5, §7, §8.

---

## 12. ADR

**Decision.** Mutualiser `veille-n8n` (déjà déployé) comme unique instance n8n
hébergeant les workflows veille + podcast, via un réseau Docker bridge
externe `podcast-bridge`. La stack podcast ne contient plus de service n8n
local et garde Postgres + Redis isolés.

**Drivers.**
- D1. Éviter une seconde instance n8n (coût RAM, double port, double clé).
- D2. Garder l'isolation d'état (Postgres / Redis distincts) pour ne pas
  mélanger les schémas et les rate limits.
- D3. Préserver le workflow veille existant SANS modification fonctionnelle.

**Alternatives considered.**
- A. **Tout fusionner dans un seul compose** (postgres unique, redis unique,
  n8n unique). Rejeté : couplage fort, blast radius DB élargi, complexité
  de re-déploiement de l'un sans l'autre.
- B. **Garder deux n8n** (statu quo). Rejeté : duplication, mission
  utilisateur explicite de mutualiser.
- C. **n8n veille via reverse proxy HTTP** (sans réseau partagé). Rejeté :
  routage HTTP/L7 ajoute un hop, complique l'auth interne (bearer token
  vs. mTLS), DNS-conteneur natif est plus simple.

**Why chosen.** Plus petit changement topologique qui répond à la mission,
réseau Docker bridge est natif et bien outillé, isolation Postgres/Redis
préservée.

**Consequences.**
- (+) -1 conteneur n8n côté podcast.
- (+) Un seul UI à monitorer.
- (-) Upgrade n8n veille_auto se propage automatiquement (R2).
- (-) Blast radius `N8N_ENCRYPTION_KEY` élargie (R3).
- (-) `N8N_ENV_VARS` expose plus de secrets aux Code nodes veille (R4).

**Follow-ups.**
- F-1. Rotation `N8N_ENCRYPTION_KEY` post-merge (procédure dédiée, hors scope).
- F-2. Pin `n8nio/n8n:2.22.3` côté veille_auto (atténue R2).
- F-3. Audit périodique des Code nodes veille (atténue R4).
- F-4. Documenter le pattern symlink `.env.podcast` dans
  `veille_auto/CLAUDE.md` si l'option A est retenue.
