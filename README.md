# Podcast Pipeline — Discord → NotebookLM

Pipeline automatisé Discord → NotebookLM pour générer des podcasts et vidéos
à partir d'une commande slash Discord.

## Présentation

Ce système permet à des utilisateurs Discord d'envoyer la commande `/podcast`
avec un sujet, un mode (`podcast` ou `video`) et un style optionnel.
Le pipeline :

1. Valide la requête et accuse réception en moins de 3 secondes.
2. Interroge Gemini pour curate 5–15 sources pertinentes.
3. Crée un notebook NotebookLM avec ces sources via un worker Playwright.
4. Déclenche la génération audio/vidéo et télécharge l'artefact.
5. Poste le résultat dans le salon Discord d'origine.

## Prérequis

- Linux (Ubuntu 22.04 / Debian 12 / WSL2)
- Docker 24+ et Docker Compose v2
- 4 Go RAM minimum recommandé
- Un compte Google Workspace dédié (compte brûleur) pour NotebookLM
- Un bot Discord avec l'intent `MESSAGE CONTENT` et les permissions `applications.commands`
- Une clé API Gemini (`https://aistudio.google.com/app/apikey`)
- Plan NotebookLM compatible Video Overview pour `mode:video`

## Démarrage rapide

```bash
git clone <repo-url> podcast
cd podcast
chmod +x scripts/*.sh
./scripts/setup.sh        # génère .env et prépare les volumes
```

Éditez `.env` et remplissez toutes les valeurs `CHANGEME_*` et `YOUR_*`,
puis consultez [QUICKSTART.md](QUICKSTART.md) pour la procédure complète.

## Services & ports

| Service   | Image                                          | Purpose                                      | Host port          |
|-----------|------------------------------------------------|----------------------------------------------|--------------------|
| postgres  | `postgres:16-alpine`                           | State store (`podcast.*` schema)             | `127.0.0.1:${POSTGRES_PORT}` |
| redis     | `redis:7-alpine`                               | Job queue + rate-limit counters              | `127.0.0.1:${REDIS_PORT}` (internal) |
| n8n       | `n8nio/n8n:latest`                             | Trigger ingestion + Discord post-back        | `127.0.0.1:${N8N_PORT}` |
| worker    | custom (Python + Playwright)                   | Chromium, NotebookLM session, artifact dl    | internal           |
| bot       | custom (Python discord.py)                     | Discord slash-command listener               | internal           |

All host port bindings are restricted to `127.0.0.1`.
Put n8n behind a reverse proxy with TLS before exposing it to the network.

## Operations

| Task                | Command                        |
|---------------------|--------------------------------|
| Start               | `./scripts/start.sh`           |
| Stop                | `./scripts/stop.sh`            |
| Restart             | `./scripts/restart.sh`         |
| Status + stats      | `./scripts/status.sh`          |
| Tail logs           | `./scripts/logs.sh {n8n,postgres,worker,bot,all}` |
| Backup DB+session   | `./scripts/backup.sh`          |
| Restore             | `./scripts/restore.sh`         |

## Backups

Backups include the Postgres `podcast.*` schema dump and an encrypted copy
of `data/session/` (storageState). The backup passphrase is set via
`BACKUP_PASSPHRASE` in `.env`.

Schedule daily backups:

```cron
0 4 * * * cd /path/to/podcast && ./scripts/backup.sh >> logs/backup.log 2>&1
```

## Troubleshooting

- **Bot does not respond to `/podcast`**: verify `DISCORD_BOT_TOKEN`, `DISCORD_APP_ID`,
  and that slash commands are registered in the correct guild (`DISCORD_GUILD_ID`).
- **Worker fails with `SESSION_EXPIRED`**: re-run `./scripts/seed-google-session.sh`
  (headed browser, operator action required). See QUICKSTART.md § "Google burner session seeding".
- **n8n webhook not reachable**: confirm `WEBHOOK_URL` is reachable from within the
  Docker network (`http://n8n:5678/` for container-to-container).
- **Gemini `429`**: reduce `RATE_LIMIT_GLOBAL_DAY` or switch `GEMINI_MODEL`.
- **`relation "podcast.jobs" does not exist`**: `db/init.sql` was not applied.
  Run `docker compose down -v && ./scripts/start.sh` (destroys data — only safe on fresh install).

## License

MIT — placeholder; update before publishing.
