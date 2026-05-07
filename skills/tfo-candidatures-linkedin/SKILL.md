---
name: tfo-candidatures-linkedin
description: "workflow de candidature automatique dans LinkedIn — architecture en phases séparées"
---

# Agent de candidature automatique — Thierry Formentini
# VERSION 8 — ATS-optimized

## ARCHITECTURE

Phases indépendantes — chaque phase dans une nouvelle conversation.

```
EASY APPLY     → Phase C directement
NON EASY APPLY → Phase B puis Phase C
```

- `/candidatures-linkedin` ou `phase-a` → Extraction batch + routage
- `/candidatures-linkedin phase-b [jobId]` → Analyse + docs adaptés (non Easy Apply uniquement)
- `/candidatures-linkedin phase-c [jobId]` → Soumission + Google Sheets

## RÈGLES GLOBALES D'ÉCONOMIE D'APPELS

1. Toujours `browser_batch` pour grouper navigate + wait.
2. Pas de screenshot intermédiaire sauf si indispensable.
3. Préférer `get_page_text` ou JS au screenshot.
4. Un seul `tabs_context_mcp` par phase, au début.
5. Grouper scroll + wait + JS en un seul `browser_batch`.

---

## PHASE A — Extraction batch + routage

### A1 — Init

```
tabs_context_mcp(createIfEmpty=true)
```

Par défaut : vérifier si page courante contient des offres :

```javascript
const hasJobs = document.querySelectorAll('a[href*="/jobs/view/"]').length > 0;
const url = window.location.href;
JSON.stringify({ hasJobs, url: url.slice(0, 80) });
```

- `hasJobs = true` → continuer vers A2.
- `hasJobs = false` OU flag `-navig` → naviguer :

```
browser_batch([navigate(url="https://www.linkedin.com/notifications/?filter=jobs_all"), wait(3s)])
```

### A2 — Scroll + extraction JS

```
browser_batch([scroll(down,10), wait(1s), scroll(down,10), wait(1s), scroll(down,10), wait(2s)])
```

```javascript
const notifications = [];
document.querySelectorAll('[data-urn], li, .nt-card').forEach(el => {
  const text = el.innerText || '';
  if (/Neue Jobangebote/i.test(text)) return;
  Array.from(el.querySelectorAll('a[href]')).forEach(a => {
    const m = a.href.match(/\/jobs\/view\/(\d+)/);
    if (m) notifications.push({ jobId: m[1], snippet: text.slice(0, 120).replace(/\n/g,' ') });
  });
});
const seen = new Set();
JSON.stringify(notifications.filter(n => { if(seen.has(n.jobId)) return false; seen.add(n.jobId); return true; }));
```

### A3 — Filtrage

- "Neue Jobangebote" (pluriel) → SKIP
- "Neues Jobangebot" (singulier) + entreprise → traiter

⚠️ Ne jamais naviguer vers linkedin.com/jobs/search/

### A4 — Type d'offre (1 browser_batch par offre)

```
browser_batch([navigate(url="https://www.linkedin.com/jobs/view/[jobId]/"), wait(2s)])
```

```javascript
const btn = document.querySelector('.jobs-apply-button');
const btnText = btn?.innerText?.trim() || '';
const hasExternalIcon = !!btn?.querySelector('[data-test-icon="link-external-small"]');
const isExternal = hasExternalIcon || !!document.querySelector('.jobs-apply-button--external') || btnText.includes('↗');
const isEasyApply = !isExternal && (btnText.includes('Einfach bewerben') || btnText.includes('Easy Apply'));
const title = document.querySelector('.job-details-jobs-unified-top-card__job-title, h1')?.innerText?.trim() || '';
const company = document.querySelector('.job-details-jobs-unified-top-card__company-name, .topcard__org-name-link')?.innerText?.trim() || '';
const desc = document.querySelector('.jobs-description, .job-view-layout')?.innerText?.slice(0, 800) || '';
JSON.stringify({ isEasyApply, isExternal, title, company, desc });
```

| Type | Action |
|---|---|
| `isEasyApply` | → Phase C directement |
| `isExternal` | → Phase B puis Phase C |

### A5 — Boucle séquentielle

Traiter UNE offre à la fois. Pour chaque Easy Apply : Phase C complète → attendre 30s → suivante.
Les non Easy Apply : lister dans le résumé, traiter manuellement via Phase B.

### A6 — Résumé

```
EASY APPLY soumises : [jobId] — [Entreprise] — [Titre] — STATUT
NON EASY APPLY : /candidatures-linkedin phase-b [jobId]
```

---

## PHASE B — Analyse + génération documents

⚠️ Nouvelle session. Non Easy Apply uniquement.

### B1 — Récupérer l'offre

```
tabs_context_mcp(createIfEmpty=true)
browser_batch([navigate(url="https://www.linkedin.com/jobs/view/[jobId]/"), wait(3s)])
```

Puis `get_page_text`.

### B2 — Analyse et génération

Le prompt système du Project exécute : Étape 1 (analyse poste) → Étape 2 (scoring + must-have) → Étape 3 (optimisation) → **ATS** → Étape 4 (verdict + PDF).

---

## OPTIMISATION ATS — OBLIGATOIRE avant génération CV

### ATS-1 — Extraire les termes cibles

**Liste A — must-match (présence obligatoire) :**
- Intitulés de poste exacts
- Technologies nommées (SAP, Salesforce, Azure…)
- Frameworks/certifications explicites (ITIL, NIS2, SOX, ISO 27001…)
- Mots-clés domaine discriminants

**Liste B — secondaires (présence souhaitable) :**
- Synonymes proches non encore présents
- Verbes d'action de l'offre

### ATS-2 — Mapping terme par terme

Pour chaque terme Liste A : vérifier présence **mot-à-mot** dans le CV adapté.

**Substituer si :** terme offre = exactement ce que Thierry a fait → remplacer le terme CV par le terme offre.
**Ne pas substituer si :** terme plus précis que l'expérience réelle (risque entretien) ou version différente (ex. SAP R/3 ≠ SAP S/4HANA).

Exemples autorisés : "vendor steering" → "Vendor Management" · "IT strategic roadmap" → "IT-Strategie & Roadmap"
Exemples interdits : inventer "DevOps", substituer "SAP R/3" par "SAP S/4HANA"

### ATS-3 — Densité et placement

- Chaque terme Liste A : présent **au moins 1x** dans les bullets des 2-3 postes les plus pertinents
- `tagline` : contient les 2-3 termes les plus discriminants
- `expertise` + `competencies` sidebar : termes **exacts** de l'offre, pas paraphrases
- `profile` sidebar : minimum 2 termes Liste A
- Cible densité : chaque terme Liste A présent **2-3x** au total (tagline + sidebar + bullets)
- Ne pas forcer si contexte inadapté — keyword stuffing détecté par certains ATS

### ATS-4 — Vérification finale

Produire ce tableau avant génération PDF :

```
Terme offre          | Occurrences | Statut
[terme 1]            | 3           | ✅
[terme 2]            | 1           | ⚠️ cible 2+
[terme 3]            | 0           | ❌ MANQUANT
Score ATS : X/Y termes Liste A couverts
```

- Terme Liste A à 0 + substitution défendable → insérer avant génération
- Terme Liste A à 0 + non défendable → noter dans `===NOTES_ADAPTATION===`

---

## GÉNÉRATION CV — PROTOCOLE OBLIGATOIRE

```bash
cp /mnt/project/generate_cv.py /home/claude/generate_cv_[ENTREPRISE].py
```

### Priorités bullets

- **p=1** — jamais retiré (chiffre d'impact, compétence centrale)
- **p=2** — retiré en dernier recours
- **p=3** — retiré en premier si > 2 pages

`auto_calibrate` retire p=3 de la fin, puis p=2 si nécessaire. Minimum 1 bullet par poste.

### Workflow variante

1. Copier le script
2. Définir `CVData` avec `tagline`, `profile`, `expertise`, `competencies`, `job_overrides`, `job_order`
3. `build_pdf(variant_data, output_path)` — auto-calibration incluse
4. Vérifier pages :

```python
from pypdf import PdfReader
assert len(PdfReader(output_path).pages) == 2
```

5. Si échec → diagnostiquer :

```python
from generate_cv_[ENTREPRISE] import variant_data, _estimate_height, CONTENT_H
h = _estimate_height(variant_data)
print(f"{h:.0f} / {2*CONTENT_H:.0f} pts ({h/(2*CONTENT_H)*100:.1f}%)")
```

### Règles de contenu

**Change par variante :** tagline · profile · expertise · competencies · job_order · job_overrides (bullets 2-3 postes clés)
**Ne change jamais :** employeurs · titres · dates · chiffres · coordonnées · langues · formation · aucun poste supprimé

**Détail par pertinence :**
- Poste central → 6-8 bullets, 2-3 sous-sections
- Partiellement pertinent → 3-5 bullets, 1-2 sous-sections
- Non pertinent → 2-3 bullets p=1, pas de sous-section

**Si 3 pages après auto_calibrate :** réduire à 2 bullets les postes les moins pertinents, ne jamais toucher aux p=1 centraux.
**Si page 2 < 50% :** acceptable si page 1 dense — ne pas inventer du contenu.

### B3 — Fin de phase

```
✅ PHASE B TERMINÉE
→ Télécharge les fichiers, puis nouvelle conversation :
  /candidatures-linkedin phase-c [jobId]
⚠️ CV et lettre téléchargés localement avant Phase C.
```

---

## PHASE C — Soumission + Google Sheets

⚠️ Nouvelle session si appelée après Phase B. Même session si venant de Phase A.

### C1 — Décision

- Easy Apply (Phase A) → soumettre directement, aller C2
- Non Easy Apply : POSTULE → C2 · POSTULE_SI → C3 (EN_ATTENTE_VALIDATION) · NE_POSTULE_PAS → C3 (SKIPPED)

### C2 — Soumission

Si appelée manuellement : `tabs_context_mcp` puis `browser_batch([navigate jobs/view/[jobId]/], wait(2s))`.

Cliquer "Einfach bewerben" / "Easy Apply". Parcourir le formulaire :
- Contact : vérifier nom/email/tél pré-remplis, ne pas modifier, "Weiter"
- CV : Easy Apply → CV récent LinkedIn existant · Non Easy Apply → uploader `CV_Formentini_[poste].pdf`
- Questions sensibles (salaire, disponibilité) → demander confirmation à Thierry

**Easy Apply :** soumettre sans confirmation. Afficher `✅ Soumis : [Entreprise] — [Poste] — [CV]`

**Non Easy Apply :** demander confirmation explicite avant "Absenden". Attendre "oui" / "confirme".

CAPTCHA → arrêt immédiat, alerter Thierry. Erreur technique → STATUT = ERREUR, continuer.

### C3 — Google Sheets

```
browser_batch([navigate(url="https://docs.google.com/spreadsheets/d/1ezsbGvCNcg15NDTTCFNVwaWzUW86b9WuJ5GQRu7PmwE/edit"), wait(3s)])
```

Ajouter ligne : DATE · ENTREPRISE · POSTE · VERDICT · SCORE_ATS · SCORE_HUMAIN · RAISON_COURTE · STATUT · NOTES

Easy Apply : VERDICT/SCORES = N/A. Non Easy Apply : valeurs du bloc `===DECISION===`.

### C4 — Résumé

Lister : SOUMIS · EN_ATTENTE_VALIDATION · SKIPPED · ERREUR → `✅ PHASE C TERMINÉE`

---

## RÈGLES DE SÉCURITÉ

- Easy Apply : soumission automatique sans confirmation
- Non Easy Apply : confirmation explicite obligatoire avant soumission
- Jamais de données financières, mots de passe
- CAPTCHA → arrêt immédiat
- Max 10 offres par session Phase A
- 30s minimum entre deux soumissions Phase C
- Erreur → STATUT = ERREUR + description → offre suivante
