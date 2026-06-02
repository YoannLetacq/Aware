# AGENT SPAWN DIRECTIVES — Podcast Pipeline

> Directive du **DIRECTEUR** (utilisateur) au **CHEF DE PROJET** (agent
> principal). Régit **qui spawner et combien** pour faire avancer le build
> du pipeline Discord → NotebookLM, y compris sous boucle `ralph`.
> Le chef de projet **APPLIQUE** ce roster ; il ne l'élargit pas. Tout
> dépassement (agent hors roster, concurrence > plafond, writer non
> autorisé) est une **décision directeur** — STOP et remonter.
>
> Lecture préalable (read-first) pour tout agent spawné :
> `.omc/refs/conduct/AGENT_CONDUCT.md`, `.omc/refs/conduct/RISK_MANAGEMENT.md`,
> et le `CLAUDE.md` du projet.

## 0. Statut & portée

- Document émis par le directeur. Source de vérité pour **qui spawner et
  combien**. Prime sur l'habitude du chef de projet, pas sur les conduct files.
- Ce projet est en **phase de build** (Phase 1 ingestion livrée ; Phase 2+ :
  Gemini, NotebookLM, delivery). Le roster est donc **constructif** (le writer
  principal est `executor`), pas soustractif.
- Roster = **plafond**, pas un quota à remplir : spawner le **minimum suffisant**
  (`MAIN_AGENT_CONDUCT.md` §2.1 « plus petit agent compétent »).
- Les **modèles** des agents proviennent du catalogue OMC (`omc-reference`).
  Il n'y a pas de définitions locales dans `.claude/agents/` ; surcharger un
  modèle via `model=` est une décision ponctuelle, pas un défaut.

## 1. Roster autorisé (total 8 · max 4 simultanés)

| Phase | Agent | Nombre | Write ? | Rôle |
| --- | --- | --- | --- | --- |
| PLAN | `planner` | 1 | non (RO) | découpe la phase en tâches, critères d'acceptation |
| PLAN | `architect` | 1 | non (RO) | frontières de modules, contrats (envelope, lifecycle), trade-offs |
| INVENTAIRE | `explore` | 1 | non (RO) | localise le code existant à réutiliser (file:line) |
| EXÉCUTION | `executor` | 2 | **oui** | implémente une tâche TDD cohérente, 1 worktree isolé/agent |
| TEST | `test-engineer` | 1 | **oui** | stratégie + tests d'intégration/e2e, durcissement flaky |
| REVIEW | `code-reviewer` | 1 | non (RO) | revue du diff, sévérité notée |
| REVIEW | `verifier` | 1 | non* | preuve pylint 10/10 + ruff + pytest verts |
| SÉCURITÉ | `security-reviewer` | 1 | non (RO) | chemins flaggés `RISK_MANAGEMENT.md` §4.2 uniquement |

`executor` et `test-engineer` sont les seuls writers. (*le verifier constate,
il ne modifie pas le code applicatif.) `debugger`, `code-simplifier`,
`git-master`, `writer` → §4 (à la demande).

## 2. Règles de spawn

- **Brief self-contained** : objectif, fichiers + lignes, contraintes
  (les trois read-first ci-dessus), critères d'acceptation, format de sortie.
- **Read-first** : référencer `AGENT_CONDUCT.md` et `RISK_MANAGEMENT.md` dans
  CHAQUE brief pour déclencher le mandate de l'agent.
- **TDD obligatoire** (`AGENT_CONDUCT.md` §1.1) : l'`executor` écrit le test
  qui échoue avant le code. Le test fait partie du livrable, pas un ajout après.
- **Un writer = un worktree isolé** : chaque `executor`/`test-engineer` dans
  son worktree ; aucun écrasement croisé. Merge sur la branche d'intégration
  avant la barrière REVIEW.
- **Découplage author/review** (`MAIN_AGENT_CONDUCT.md`) : l'agent qui écrit
  n'est jamais celui qui approuve. Review et verify sont une passe séparée.

## 3. Concurrence & barrières

- Plafond **dur** : ≤ 4 agents en vol à tout instant.
- Phases séquentielles par tâche. Si le chef de projet **pipeline** les tâches
  (tâche A en review pendant que B s'exécute), le cumul en vol reste ≤ 4.
- **Barrière avant REVIEW** : tous les writers d'un lot terminés et leurs
  worktrees mergés proprement sur la branche d'intégration avant la revue.
- **Barrière SÉCURITÉ** : aucune tâche touchant un chemin `RISK_MANAGEMENT.md`
  §4.2 (session/storageState, Ed25519, SQL, IDOR delivery, secrets, n8n env)
  n'est déclarée terminée sans passe `security-reviewer`.

## 4. Agents utilitaires — hors roster, à la demande (autorisation directeur)

Ne comptent **pas** dans les 8 de la boucle build :
- `debugger` / `tracer` : investigation d'un échec (test rouge, job bloqué,
  delivery ratée) avant d'envoyer un `executor` corriger.
- `code-simplifier` : uniquement pour une passe de nettoyage soustractive
  dédiée (`MAIN_AGENT_CONDUCT.md` §4.5), jamais dans la même passe qu'un build.
- `git-master` : commits atomiques + intégration des worktrees.
- `writer` : doc/docstring volumineuse uniquement.

## 5. Décisions directeur intégrées

1. **Sécurité d'abord (account-ban)** : toute tâche touchant l'automation
   NotebookLM / la session Google (`worker/app/notebooklm/`, `session.py`) est
   **au moins High** (`RISK_MANAGEMENT.md` §3.1) → STOP + validation directeur
   avant exécution, jamais une optimisation « plus rapide » sans arbitrage.
2. **Idempotence & rate-limit** : toute tâche modifiant l'enqueue ou la
   delivery exige un test anti-doublon avant merge.
3. **Pas de secret en clair** : aucun `executor` n'inline un secret dans le
   code, l'`.env`, ou le JSON de workflow n8n — placeholders only.
4. **Liste des chemins sécurité §4.2 confirmée** ; tout nouveau chemin sensible
   découvert en cours de route → STOP + escalade directeur immédiate.

## 6. Garde-fous (y compris boucle ralph)

- Aucun agent hors roster §1 sans décision directeur.
- Aucun writer hors `executor` / `test-engineer` (et `code-simplifier` en passe
  dédiée).
- **Critère de sortie de boucle** : pylint 10/10 (`worker/app/` + `bot/app/`),
  ruff clean, pytest verts, et passe `code-reviewer` + `verifier` sans
  HIGH/CRITICAL ouvert. La boucle ne se déclare pas terminée tant qu'un gate
  est rouge — elle itère (`AGENT_CONDUCT.md` §3) ou remonte l'obstacle.
- Le chef de projet **signale au directeur** si la trajectoire de coût dépasse
  l'attendu (roster majoritairement `opus`) ou si la concurrence sature.
