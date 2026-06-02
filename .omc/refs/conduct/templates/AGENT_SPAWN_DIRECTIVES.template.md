# AGENT SPAWN DIRECTIVES — {{PROJECT_NAME}} (TEMPLATE)

> Reusable template. Replace every `{{PLACEHOLDER}}`, then save as
> `AGENT_SPAWN_DIRECTIVES.md`. Two roster archetypes are provided — pick the
> one matching the cycle (§1) and delete the other.
>
> Directive du **DIRECTEUR** (utilisateur) au **CHEF DE PROJET** (agent
> principal). Régit **qui spawner et combien**. Le chef de projet **APPLIQUE**
> ce roster ; il ne l'élargit pas. Tout dépassement = décision directeur → STOP.
>
> Lecture préalable (read-first) pour tout agent spawné : {{GOVERNANCE_FILES}}.

## Légende des placeholders

| Placeholder | Sens |
| --- | --- |
| `{{PROJECT_NAME}}` | Nom du projet |
| `{{CYCLE_TYPE}}` | `BUILD` (constructif) ou `CLEANUP` (soustractif) |
| `{{TOTAL_AGENTS}}` / `{{MAX_CONCURRENT}}` | Roster total / concurrence max |
| `{{GOVERNANCE_FILES}}` | Fichiers read-first dans CHAQUE brief |
| `{{INTEGRATION_BRANCH}}` | Branche d'intégration des worktrees |
| `{{N_*}}` | Nombre d'agents par rôle (somme = `{{TOTAL_AGENTS}}`) |
| `{{PRINCIPAL_FLOW}}` | Flux e2e pour la parité qa |
| `{{SECURITY_PATHS}}` | Chemins sensibles (renvoi `RISK_MANAGEMENT.md` §4.2) |
| `{{DIRECTOR_DECISIONS}}` | Décisions directeur spécifiques au projet |

---

## 0. Statut & portée
- Source de vérité pour **qui spawner et combien**. Prime sur l'habitude du
  chef de projet, pas sur les conduct files.
- Roster = **plafond**, pas un quota : spawner le **minimum suffisant**
  (`MAIN_AGENT_CONDUCT.md` §2.1).
- Modèles : catalogue OMC (`omc-reference`). `model=` est une décision ponctuelle.
- Cycle courant : **{{CYCLE_TYPE}}**.

## 1A. Roster BUILD (constructif — writer = `executor`)
*Utiliser pour un build de feature / phase. Supprimer §1B.*

| Phase | Agent | Nombre | Write ? | Rôle |
| --- | --- | --- | --- | --- |
| PLAN | `planner` | {{N_PLANNER}} | non | découpe + critères d'acceptation |
| PLAN | `architect` | {{N_ARCHITECT}} | non | frontières, contrats, trade-offs |
| INVENTAIRE | `explore` | {{N_EXPLORE}} | non | localise le code réutilisable (file:line) |
| EXÉCUTION | `executor` | {{N_EXECUTOR}} | **oui** | implémente une tâche TDD, 1 worktree/agent |
| TEST | `test-engineer` | {{N_TEST}} | **oui** | tests d'intégration/e2e, anti-flaky |
| REVIEW | `code-reviewer` | {{N_REVIEWER}} | non | revue du diff, sévérité notée |
| REVIEW | `verifier` | {{N_VERIFIER}} | non* | preuve gates verts |
| SÉCURITÉ | `security-reviewer` | {{N_SECREV}} | non | chemins `RISK_MANAGEMENT.md` §4.2 |

Writers = `executor` + `test-engineer` uniquement.

## 1B. Roster CLEANUP (soustractif — writer = `code-simplifier`)
*Utiliser pour une passe de nettoyage. Supprimer §1A.*

| Phase | Agent | Nombre | Write ? | Rôle |
| --- | --- | --- | --- | --- |
| INVENTAIRE | `explore` | {{N_EXPLORE}} | non | 1 sous-arbre/agent, liste file:line |
| TRIAGE | `architect` | {{N_ARCHITECT}} | non | verdict/item : nettoyer / laisser / escalader |
| EXÉCUTION | `code-simplifier` | {{N_SIMPLIFIER}} | **oui** | items approuvés, 1 worktree/agent |
| REVIEW | `code-reviewer` | {{N_REVIEWER}} | non | revue du diff |
| REVIEW | `verifier` | {{N_VERIFIER}} | non* | preuve tests/parité |
| SÉCURITÉ | `security-reviewer` | {{N_SECREV}} | non | chemins §4.2 uniquement |
| QA | `qa-tester` | {{N_QA}} | non* | run interactif sur {{PRINCIPAL_FLOW}} |

Writer unique = `code-simplifier`. (*read-only en pratique : ces agents
constatent, ne modifient pas le code applicatif.)

## 2. Règles de spawn
- **Brief self-contained** : objectif, fichiers + lignes, contraintes
  ({{GOVERNANCE_FILES}}), critères d'acceptation, format de sortie.
- **Read-first** : référencer {{GOVERNANCE_FILES}} dans CHAQUE brief.
- **TDD** (BUILD) : le test qui échoue avant le code, dans le livrable.
- **Un writer = un worktree isolé** ; merge sur `{{INTEGRATION_BRANCH}}` avant
  la barrière REVIEW. Aucun écrasement croisé.
- **Author ≠ reviewer** : la passe review/verify est distincte de l'auteur.

## 3. Concurrence & barrières
- Plafond **dur** : ≤ {{MAX_CONCURRENT}} agents en vol.
- Pipeline autorisé (tâche A en review pendant que B s'exécute) tant que le
  cumul reste ≤ {{MAX_CONCURRENT}}.
- **Barrière avant REVIEW** : writers du lot terminés + worktrees mergés.
- **Barrière SÉCURITÉ** : toute tâche touchant {{SECURITY_PATHS}} exige une
  passe `security-reviewer` avant d'être déclarée terminée.

## 4. Agents utilitaires — hors roster, à la demande (autorisation directeur)
Ne comptent **pas** dans les {{TOTAL_AGENTS}} :
- `debugger` / `tracer` : investigation d'un échec avant correction.
- `git-master` : commits atomiques + intégration des worktrees.
- `writer` : doc/docstring volumineuse uniquement.
- (`code-simplifier` en BUILD, `executor` en CLEANUP) : seulement sur décision
  directeur nommant le besoin.

## 5. Décisions directeur intégrées
{{DIRECTOR_DECISIONS}}

## 6. Garde-fous (y compris boucle ralph)
- Aucun agent hors roster §1 sans décision directeur ; aucun writer hors ceux
  autorisés par le cycle courant.
- **Critère de sortie de boucle** : tous les gates verts (pylint/ruff/tests) +
  passe `code-reviewer` + `verifier` sans HIGH/CRITICAL ouvert. La boucle
  n'est pas terminée tant qu'un gate est rouge — elle itère ou remonte.
- Le chef de projet **signale au directeur** si le coût dérive (roster
  majoritairement haut de gamme) ou si la concurrence sature.
