# Guide de configuration n8n — Pipeline Podcast

Runbook opérateur pour configurer l'instance n8n après que `./scripts/start.sh`
a démarré la stack. À suivre dans l'ordre des sections.

---

## 1. Prérequis

Vérifier que tous les services sont `healthy` :

```bash
docker compose ps
```

Résultat attendu : les colonnes `Status` indiquent `healthy` pour `postgres`,
`redis` et `n8n`. Si un service est `starting`, attendre 30 secondes et
relancer la commande.

S'assurer que `.env` contient des valeurs réelles (pas les placeholders
`CHANGEME_*` / `YOUR_*` de `env.template`) pour :

| Variable               | Source                                              |
|------------------------|-----------------------------------------------------|
| `DISCORD_BOT_TOKEN`    | Discord Developer Portal → Bot → Token             |
| `DISCORD_APP_ID`       | Discord Developer Portal → General Information     |
| `DISCORD_PUBLIC_KEY`   | Discord Developer Portal → General Information     |
| `DISCORD_GUILD_ID`     | ID du serveur Discord cible                        |
| `GEMINI_API_KEY`       | https://aistudio.google.com/app/apikey              |
| `POSTGRES_USER`        | valeur choisie lors du `setup.sh`                  |
| `POSTGRES_PASSWORD`    | valeur générée lors du `setup.sh`                  |
| `POSTGRES_DB`          | valeur choisie lors du `setup.sh`                  |

L'opérateur doit avoir accès administrateur à l'application Discord (pour
enregistrer la slash-command à l'étape 6).

---

## 2. Premier accès n8n

Ouvrir `http://localhost:5678/` dans un navigateur.

Au premier démarrage, n8n affiche un wizard de création de compte propriétaire.
Renseigner une **adresse email locale** et un **mot de passe local** — ces
identifiants sont propres à l'instance n8n et n'ont aucun lien avec les
credentials Discord ou Google contenus dans `.env`. Les conserver dans un
gestionnaire de mots de passe.

> Note : `N8N_BASIC_AUTH_*` est un mécanisme legacy non utilisé dans cette
> stack. L'authentification se fait uniquement via le compte propriétaire
> créé ici.

---

## 3. Vérifier l'accès aux variables d'environnement dans les Code nodes

`N8N_BLOCK_ENV_ACCESS_IN_NODE=false` est positionné dans `docker-compose.yml`,
et `N8N_ENV_VARS` liste les noms autorisés. Pour confirmer que n8n a bien
chargé les variables :

Créer un workflow de test temporaire avec un **Manual Trigger** suivi d'un
**Code node** contenant :

```javascript
return [{ json: {
  hasBot:    !!$env.DISCORD_BOT_TOKEN,
  hasGemini: !!$env.GEMINI_API_KEY
}}];
```

Exécuter avec **Test workflow**. Résultat attendu :

```json
{ "hasBot": true, "hasGemini": true }
```

Si l'un des champs est `false`, n8n n'a pas chargé la variable. Relancer le
conteneur :

```bash
docker compose restart n8n
```

Puis re-tester. Supprimer le workflow de test une fois la vérification faite.

---

## 4. Créer les credentials

Naviguer vers **Settings → Credentials → New** pour chaque credential ci-dessous.

### Postgres

Type : **Postgres**

| Champ    | Valeur                            |
|----------|-----------------------------------|
| Host     | `postgres`                        |
| Port     | `5432`                            |
| Database | valeur de `POSTGRES_DB` dans `.env`  |
| User     | valeur de `POSTGRES_USER` dans `.env` |
| Password | valeur de `POSTGRES_PASSWORD` dans `.env` |
| SSL      | `disable`                         |

Cliquer **Test connection** avant de sauvegarder. Le host doit être `postgres`
(nom du service Docker), pas `localhost`.

### Redis

Type : **Redis**

| Champ    | Valeur  |
|----------|---------|
| Host     | `redis` |
| Port     | `6379`  |
| DB Index | `0`     |
| Password | valeur de `REDIS_PASSWORD` dans `.env` |

> **Nouveau** : Redis exige désormais un mot de passe (`requirepass`).
> Renseigner le champ **Password** avec la valeur de `REDIS_PASSWORD`
> depuis votre `.env`. Sans ce champ, la connexion sera rejetée.

Cliquer **Test connection** avant de sauvegarder.

### Discord Bot Token

Type : **Header Auth**

Nommer le credential `Discord Bot Token`.

| Champ       | Valeur                          |
|-------------|---------------------------------|
| Header Name | `Authorization`                 |
| Header Value | `Bot {{ $env.DISCORD_BOT_TOKEN }}` |

La syntaxe `{{ $env.DISCORD_BOT_TOKEN }}` est une expression n8n — n8n
l'évalue à l'exécution, la valeur réelle du token n'est pas stockée en clair
dans le credential.

### Gemini API Key

Type : **Header Auth** (recommandé) ou **Query Auth**

**Option A — Header Auth** (recommandée, correspond au pattern de
`veille_auto/workflow-simplified.json`) :

Nommer le credential `Gemini API Key`.

| Champ       | Valeur                        |
|-------------|-------------------------------|
| Header Name | `x-goog-api-key`              |
| Header Value | `={{ $env.GEMINI_API_KEY }}` |

**Option B — Query Auth** (pattern `?key=`) :

| Champ      | Valeur                       |
|------------|------------------------------|
| Query Name | `key`                        |
| Query Value | `={{ $env.GEMINI_API_KEY }}` |

Les deux fonctionnent avec l'API Gemini. L'option A est préférée car elle ne
fait pas apparaître la clé dans les URLs de log.

---

## 5. Importer le workflow

Phase 1 livre `workflows/pipeline.json`. Importer via :

**Workflows → Import from File** → sélectionner `workflows/pipeline.json`.

Après l'import, n8n affiche les nœuds avec des avertissements
"credential not configured". Cliquer sur chaque nœud concerné et lier le
credential créé à l'étape 4 :

- Nœuds Postgres → credential **Postgres**
- Nœuds Redis → credential **Redis**
- Nœuds HTTP vers Discord → credential **Discord Bot Token**
- Nœuds HTTP vers Gemini → credential **Gemini API Key**

Vérifier qu'il ne reste **aucun** avertissement jaune sur les nœuds.

Activer le workflow avec le **toggle en haut à droite** (passe de `Inactive`
à `Active`). L'activation génère les URLs webhook Production.

---

## 6. Enregistrer la slash-command Discord

Opération unique. Nécessite `DISCORD_BOT_TOKEN`, `DISCORD_APP_ID` et
`DISCORD_GUILD_ID` chargés dans le shell :

```bash
source .env
```

Phase 1 livre `workflows/discord-command.json`. Enregistrer la commande en
scope guild (propagation immédiate, contrairement au scope global qui peut
prendre jusqu'à une heure) :

```bash
curl -X POST \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  "https://discord.com/api/v10/applications/$DISCORD_APP_ID/guilds/$DISCORD_GUILD_ID/commands" \
  -d @workflows/discord-command.json
```

Le fichier `discord-command.json` déclare le schéma `/podcast` :

```json
{
  "name": "podcast",
  "description": "Générer un podcast ou une vidéo NotebookLM",
  "options": [
    {
      "name": "subject",
      "description": "Sujet (40–400 caractères)",
      "type": 3,
      "required": true,
      "min_length": 40,
      "max_length": 400
    },
    {
      "name": "mode",
      "description": "Type de sortie",
      "type": 3,
      "required": true,
      "choices": [
        {"name": "Podcast audio", "value": "podcast"},
        {"name": "Vidéo", "value": "video"}
      ]
    },
    {
      "name": "style",
      "description": "Style vidéo (requis si mode=video)",
      "type": 3,
      "required": false
    }
  ]
}
```

Voir `ARCHITECTURE.md §3.1` pour le schéma complet du payload Discord → n8n.

---

## 7. Configurer le webhook entrant

Après activation du workflow (étape 5), ouvrir le nœud **Webhook** dans
l'éditeur. Le champ **Production URL** affiche l'URL générée par n8n, de la
forme :

```
http://localhost:5678/webhook/podcast
```

**Architecture recommandée (bot-first) :** router les interactions Discord vers
le conteneur `bot` en premier. Le bot (`bot/app/main.py`) gère la vérification
Ed25519 (`DISCORD_PUBLIC_KEY`) et relaie vers n8n via
`bot/app/webhook_client.py`. C'est la configuration que Phase 1 implémente.
La signature cryptographique reste dans du code Python contrôlé, pas dans un
Code node n8n.

**Architecture alternative (n8n direct) :** pointer l'Interactions Endpoint URL
de l'application Discord directement sur l'URL webhook n8n. Dans ce cas n8n
doit répondre au PING Discord avec `{ "type": 1 }` via un Code node. Cette
option est plus fragile car le vérificateur Ed25519 doit être implémenté en
JavaScript dans n8n.

Pour l'architecture bot-first, aucune configuration manuelle du webhook n8n
dans le portail Discord n'est nécessaire — le bot gère la réception.

---

## 8. Tester de bout en bout

Dans un canal Discord du serveur configuré :

```
/podcast subject:"Test n8n setup — vérification pipeline Phase 1" mode:podcast
```

**Vérifications attendues :**

1. Dans les 2 secondes : réponse éphémère "Reçu — génération en cours…" dans Discord.

2. Vérifier la présence du job en base :

```bash
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "SELECT id, status, subject FROM podcast.jobs ORDER BY created_at DESC LIMIT 1;"
```

La ligne doit avoir `status = queued`.

3. Vérifier la présence dans la queue Redis :

```bash
docker compose exec redis redis-cli LLEN podcast:jobs
```

Valeur attendue : `≥ 1`.

Phase 1 s'arrête ici. Les étapes Gemini et NotebookLM sont traitées en
Phase 2+ (voir `IMPLEMENTATION_PLAN.md §2`).

---

## 9. Dépannage

| Symptôme | Cause probable | Action |
|----------|---------------|--------|
| `$env.X` retourne `undefined` dans un Code node | Variable absente de `N8N_ENV_VARS` | Ajouter `X` à `N8N_ENV_VARS` dans `docker-compose.yml`, puis `docker compose restart n8n` |
| Test connection Postgres échoue | Host configuré à `localhost` au lieu de `postgres` | Corriger le credential : Host = `postgres` |
| Workflow reste `Inactive`, pas d'URL Production | Nœud Webhook sans URL visible | Sauvegarder le workflow une première fois, puis activer |
| Vérification endpoint Discord échoue (PING rejeté) | `DISCORD_PUBLIC_KEY` absent ou incorrect dans le conteneur `bot` | Vérifier `.env`, puis `docker compose logs bot` pour le message d'erreur Ed25519 |
| `LPUSH` depuis un Code node échoue | Credential Redis non lié au nœud | Lier le credential **Redis** dans le nœud, ou utiliser un nœud natif **Redis** (operation: List Push) — pattern identique à `veille_auto/workflow-simplified.json` nœud "Acquire Lock" |
| `podcast-postgres` redémarre en boucle avec `initdb: directory exists but is not empty` | Un fichier dot-préfixé (`.gitkeep`, `.DS_Store`, artefact WSL) est présent à la racine du bind-mount `/var/lib/postgresql/data` | La stack utilise `PGDATA=/var/lib/postgresql/data/pgdata` (sous-répertoire) pour isoler initdb du contenu du répertoire parent. Les données Postgres réelles se trouvent dans `data/postgres/pgdata/`, pas à la racine de `data/postgres/`. Le fichier `data/postgres/.gitkeep` est intentionnel et ne doit pas être supprimé — il est ignoré par initdb grâce au PGDATA subdir. En cas de répertoire corrompu (UID 70 mode 0700), nettoyer avec `docker run --rm -v $(pwd)/data/postgres:/pgdata alpine sh -c 'rm -rf /pgdata/* /pgdata/.[!.]*'` puis relancer `./scripts/start.sh`. |

---

## 10. Maintenance

Scripts de maintenance disponibles :

- **`scripts/backup.sh`** — sauvegarde chiffrée Postgres + volumes n8n + session.
  Planifier via cron :
  ```bash
  # Exemple : sauvegarde quotidienne à 4h
  0 4 * * * cd /home/yoann/podcast && ./scripts/backup.sh >> data/logs/backup.log 2>&1
  ```

- **`scripts/seed-google-session.sh`** — rafraîchissement interactif de la
  session navigateur (login Playwright → `storageState.json`). Runbook
  complet en Phase 3 ; à exécuter manuellement quand le worker rapporte
  `SESSION_EXPIRED`.

Références design :
- `IMPLEMENTATION_PLAN.md` — plan phasé complet (Phase 0–5).
- `ARCHITECTURE.md` — topologie des conteneurs, contrats de données, modèle
  d'état `podcast.jobs`, surface des secrets (§5).
