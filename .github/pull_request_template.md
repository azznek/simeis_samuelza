## Résumé des changements

- Mise en place de la CI complète pour un projet Rust :
  - Tests automatiques (`cargo test`)
  - Linting (`cargo clippy`)
  - Format (`cargo fmt`)
  - Build release conditionnel (`main` uniquement)
  - Compilation automatique de la documentation Typst

- Mise en place de la mise à jour automatique des dépendances (`DIY Dependabot`) :
  - `cargo update`
  - `cargo install-update -a`
  - Création de PR automatique si changements détectés

- Définition de propriétaires de code via `CODEOWNERS` :
  - Assignation automatique de reviewers en fonction des fichiers modifiés

- Mise en place de règles de protection de branche :
  - PR obligatoire
  - Validation des checks avant merge
  - Interdiction de merger sans validation d’un reviewer

---

## Objectif de cette PR

- [x] Tests
- [x] Lint + Format
- [x] CI Rust optimisée
- [x] Automatisation des updates de dépendances
- [x] Sécurité du repo (code owners + branch protection)
- [x] Documentation

---

## Checklist qualité

- [x] La PR a un titre clair et explicite
- [x] Le code est formaté (`cargo fmt`)
- [x] Le lint passe sans warning (`cargo clippy`)
- [x] Les tests unitaires passent (`cargo test`)
- [x] La documentation Typst compile
- [x] La CI passe entièrement
- [x] Les reviewers sont bien assignés automatiquement

---



## Notes complémentaires

- Pour installer Typst dans GitHub Actions, on passe par `curl + tar` car `apt` ne le propose pas sous Ubuntu 24.04.
- Le système de release est conditionné au push sur la branche `main`.
- Le workflow Dependabot personnalisé se déclenche chaque lundi ou manuellement via `workflow_dispatch`.
