# tfo-tools

Outils et skills Claude pour Thierry Formentini — versionning et archivage.

## Structure

```
tfo-tools/
├── skills/
│   └── tfo-candidatures-linkedin/
│       ├── SKILL.md          ← version active (à installer dans Claude)
│       ├── SKILL_v6.md       ← version 6 (archivée)
│       └── SKILL_v7.md       ← version 7 (CV paramétrique + auto-calibration)
└── cv-generator/
    ├── generate_cv_v3.py     ← script original (ReportLab, CV de base)
    └── generate_cv_v4.py     ← script refactorisé (modulaire, auto-calibration, variantes)
```

## Skills — tfo-candidatures-linkedin

Workflow de candidature automatique LinkedIn en 3 phases :
- **Phase A** — extraction batch des offres + routage Easy Apply / non Easy Apply
- **Phase B** — analyse CV vs offre, scoring, génération CV adapté + lettre
- **Phase C** — soumission + mise à jour Google Sheets

### Changelog

| Version | Date | Changements |
|---|---|---|
| v6 | 2025-04 | Workflow initial — deux flux selon type d'offre |
| v7 | 2026-05 | Génération CV paramétrique + auto-calibration 2 pages + protocole Phase B |

### Installation d'un skill

Copier le contenu de `SKILL.md` (ou la version voulue) dans :
`/mnt/skills/user/tfo-candidatures-linkedin/SKILL.md`

## CV Generator

### generate_cv_v4.py — usage

```bash
# CV de base
python generate_cv_v4.py

# Variante pour une offre spécifique
python generate_cv_v4.py --job HASCO

# Chemin de sortie custom
python generate_cv_v4.py --job HASCO --output /tmp/cv_hasco.pdf
```

### Ajouter une variante

Dans `generate_cv_v4.py`, ajouter une entrée dans `VARIANTS` :

```python
MON_OFFRE_CV = _make_variant(
    job_key='MON_OFFRE',
    tagline='Titre adapté · Compétence clé · Contexte',
    profile=[...],
    expertise=[...],
    competencies=[...],
    job_overrides={4: JobEntry(...)},   # index dans BASE_CV.jobs
    job_order=[4, 1, 0, 5, 3, 6, 7, 2] # postes les plus pertinents en premier
)

VARIANTS['MON_OFFRE'] = MON_OFFRE_CV
```

### Priorités des bullets

- `priority=1` — jamais retiré (chiffres d'impact, compétences centrales)
- `priority=2` — retiré en dernier recours
- `priority=3` — retiré en premier si contenu > 2 pages
