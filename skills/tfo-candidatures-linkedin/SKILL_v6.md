---
name: tfo-candidatures-linkedin
description: "workflow de candidature automatique dans LinkedIn — architecture en phases séparées"
---




# Agent de candidature automatique — Thierry Formentini
# VERSION 6 — deux flux selon type d'offre + détection automatique page courante

## ARCHITECTURE GÉNÉRALE

Le workflow est découpé en **phases indépendantes**.
**Chaque phase DOIT être lancée dans une nouvelle conversation séparée.**
Raison : chaque conversation a une limite d'appels d'outils. Travailler par phase évite le blocage.

### RÈGLE FONDAMENTALE — DEUX FLUX SELON TYPE D'OFFRE

```
Offre EASY APPLY     → Phase C directement (CV LinkedIn actif, sans customisation)
Offre NON EASY APPLY → Phase B (analyse + docs adaptés) PUIS Phase C (soumission)
```

- `/candidatures-linkedin phase-a` → Extraction batch + routage selon type d'offre
- `/candidatures-linkedin phase-b [jobId]` → Analyse CV + génération documents (offres non Easy Apply uniquement)
- `/candidatures-linkedin phase-c [jobId]` → Soumission + Google Sheets

Si l'utilisateur tape juste `/candidatures-linkedin` sans argument → lancer Phase A automatiquement.

---

## RÈGLES GLOBALES D'ÉCONOMIE D'APPELS

1. **Toujours utiliser `browser_batch`** pour grouper : navigate + wait en 1 appel.
2. **Jamais de screenshot intermédiaire** sauf si indispensable pour décider de l'étape suivante.
3. **Préférer `get_page_text` ou JS** à un screenshot quand le visuel n'apporte rien.
4. **Un seul `tabs_context_mcp`** par phase, au tout début.
5. **Grouper scroll + wait + JS** en un seul `browser_batch` quand c'est possible.

---

## PHASE A — Extraction batch + détection + routage

**⚠️ NOUVELLE SESSION OBLIGATOIRE — ouvre une nouvelle conversation avant de lancer Phase A.**

**Objectif : identifier toutes les offres nominatives, détecter leur type, et router vers le bon flux.**
**Budget cible : ≤ 15 appels d'outils pour toute la phase.**

### A1 — Init (1 appel)

```
tabs_context_mcp(createIfEmpty=true)
```

**Règle de démarrage — IMPORTANT :**

- **Par défaut** (aucun flag) : exécuter d'abord le JS de détection suivant pour vérifier si la page courante contient des offres d'emploi :

```javascript
const hasJobs = document.querySelectorAll('a[href*="/jobs/view/"]').length > 0;
const url = window.location.href;
const isJobsPage = /linkedin\.com\/(notifications|jobs)/.test(url);
JSON.stringify({ hasJobs, isJobsPage, url: url.slice(0, 80) });
```

**Règle de décision :**
- Si `hasJobs = true` → page valide, continuer vers A2 directement.
- Si `hasJobs = false` OU page vide OU URL non-LinkedIn → naviguer vers les notifications :

```
browser_batch([
  navigate(url="https://www.linkedin.com/notifications/?filter=jobs_all"),
  wait(3s)
])
```

Puis continuer avec A2.

- **Flag `-navig`** (l'utilisateur a tapé `/candidatures-linkedin phase-a -navig`) : naviguer directement vers les notifications sans vérification préalable :

```
browser_batch([
  navigate(url="https://www.linkedin.com/notifications/?filter=jobs_all"),
  wait(3s)
])
```

Puis continuer avec A2.

### A2 — Scroll complet + extraction JS (2 appels)

```
browser_batch([
  scroll(down, 10), wait(1s),
  scroll(down, 10), wait(1s),
  scroll(down, 10), wait(2s)
])
```

Puis **un seul appel JS** pour tout extraire :

```javascript
const notifications = [];
document.querySelectorAll('[data-urn], li, .nt-card').forEach(el => {
  const text = el.innerText || '';
  const isGeneric = /Neue Jobangebote/i.test(text);
  if (isGeneric) return;
  const links = Array.from(el.querySelectorAll('a[href]'));
  links.forEach(a => {
    const m = a.href.match(/\/jobs\/view\/(\d+)/);
    if (m) notifications.push({ jobId: m[1], snippet: text.slice(0, 120).replace(/\n/g,' ') });
  });
});
const seen = new Set();
const unique = notifications.filter(n => { if(seen.has(n.jobId)) return false; seen.add(n.jobId); return true; });
JSON.stringify(unique);
```

### A3 — Filtrage nominatif

**TYPE 1 — Alerte générique** → texte contient "Neue Jobangebote" (pluriel) → **SKIP immédiat**
**TYPE 2 — Offre nominative** → texte contient entreprise + "Neues Jobangebot" (singulier) → **traiter**

⚠️ Ne jamais naviguer vers linkedin.com/jobs/search/ — rester sur /notifications/

### A4 — Vérification du type d'offre (1 appel par offre nominative)

Pour chaque offre nominative, **un seul `browser_batch`** :

```
browser_batch([
  navigate(url="https://www.linkedin.com/jobs/view/[jobId]/"),
  wait(2s)
])
```

Puis JS combiné (titre + entreprise + type bouton) :

```javascript
const btn = document.querySelector('.jobs-apply-button');
const btnText = btn?.innerText?.trim() || '';
const hasExternalIcon = !!btn?.querySelector('[data-test-icon="link-external-small"]');
const isExternal = hasExternalIcon
  || !!document.querySelector('.jobs-apply-button--external')
  || btnText.includes('↗');
const isEasyApply = !isExternal && (btnText.includes('Einfach bewerben') || btnText.includes('Easy Apply'));
const title = document.querySelector('.job-details-jobs-unified-top-card__job-title, h1')?.innerText?.trim() || '';
const company = document.querySelector('.job-details-jobs-unified-top-card__company-name, .topcard__org-name-link')?.innerText?.trim() || '';
const descEl = document.querySelector('.jobs-description, .job-view-layout');
const desc = descEl?.innerText?.slice(0, 800) || '';
JSON.stringify({ isEasyApply, isExternal, title, company, desc });
```

**ROUTAGE :**

| Type détecté | Action |
|---|---|
| `isEasyApply = true` | → **Phase C directement** (CV LinkedIn actif, sans customisation) |
| `isExternal = true` | → **Phase B** (analyse + docs) **puis Phase C** (soumission manuelle) |

### A5 — Boucle de traitement séquentiel

**RÈGLE FONDAMENTALE : traiter les offres UNE PAR UNE, dans l'ordre.**
Ne jamais charger toute la liste d'un coup — cela dépasse la capacité de la session.

**Pour chaque offre Easy Apply détectée :**
1. Exécuter Phase C complètement pour cette offre (soumission + Google Sheets)
2. Attendre 30 secondes minimum
3. Passer à l'offre Easy Apply suivante
4. Répéter jusqu'à épuisement de la liste

**Aucune intervention de Thierry requise entre les offres Easy Apply.**

**Pour les offres non Easy Apply :** ne pas traiter dans cette session. Les lister dans le résumé final pour traitement manuel via Phase B.

### A6 — Résumé Phase A

Afficher en fin de session :

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ PHASE A TERMINÉE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EASY APPLY (traitées automatiquement) :
  • [jobId] — [Entreprise] — [Titre] — STATUT

NON EASY APPLY (à traiter manuellement) :
  • [jobId] — [Entreprise] — [Titre]
    → Ouvre une nouvelle conversation et tape :
       /candidatures-linkedin phase-b [jobId]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## PHASE B — Analyse CV + génération documents (offres NON Easy Apply uniquement)

**⚠️ NOUVELLE SESSION OBLIGATOIRE — ouvre une nouvelle conversation avant de lancer Phase B.**
**⚠️ Phase B ne s'applique QU'AUX offres non Easy Apply (ATS externe).**

**Déclencheur : `/candidatures-linkedin phase-b [jobId]`**

### B1 — Récupérer la description complète (2 appels)

```
tabs_context_mcp(createIfEmpty=true)
```

Puis :
```
browser_batch([
  navigate(url="https://www.linkedin.com/jobs/view/[jobId]/"),
  wait(3s)
])
```

Puis : `get_page_text` pour récupérer la description complète.

### B2 — Analyse et génération (zéro appel browser supplémentaire)

Le prompt système du Project prend le relais et exécute :
- Étape 1 : Analyse du poste
- Étape 2 : Scoring CV vs poste + vérification interactive des must-have manquants
- Étape 3 : Optimisation honnête
- Étape 4 : Verdict + génération CV adapté (PDF) + lettre de motivation (PDF)

Les fichiers sont disponibles en téléchargement dans la réponse.

Noter le bloc `===DECISION===` pour Phase C si soumission manuelle souhaitée ensuite.

### B3 — Fin de phase

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ PHASE B TERMINÉE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Télécharge les fichiers ci-dessus, puis ouvre une NOUVELLE conversation et tape :

  /candidatures-linkedin phase-c [jobId]

⚠️ Prérequis : CV et lettre téléchargés localement avant de lancer Phase C.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## PHASE C — Soumission + Google Sheets

**⚠️ NOUVELLE SESSION OBLIGATOIRE si appelée manuellement après Phase B.**
**Quand appelée depuis Phase A (flux Easy Apply) : s'exécute dans la même session.**

**Déclencheurs :**
- Automatique depuis Phase A pour chaque offre **Easy Apply**
- Manuel : `/candidatures-linkedin phase-c [jobId]` après Phase B pour offres **non Easy Apply**

### C1 — Agir selon le type d'offre et le verdict

**Flux Easy Apply (venant de Phase A) :**
→ Pas de verdict Phase B. Soumettre directement avec le CV actif LinkedIn. Aller en C2.

**Flux non Easy Apply (venant de Phase B) :**
- Si VERDICT = NE_POSTULE_PAS → Ne rien soumettre. Aller directement à C3 (STATUT = SKIPPED).
- Si VERDICT = POSTULE_SI → Ne pas soumettre. Aller directement à C3 (STATUT = EN_ATTENTE_VALIDATION).
- Si VERDICT = POSTULE → Continuer vers C2.

### C2 — Soumission Easy Apply

La page du job est déjà chargée si on vient de Phase A.
Si appelée manuellement :

```
tabs_context_mcp(createIfEmpty=true)
```

Puis :

```
browser_batch([
  navigate(url="https://www.linkedin.com/jobs/view/[jobId]/"),
  wait(2s)
])
```

**Cliquer sur "Einfach bewerben" / "Easy Apply".**

Parcourir le formulaire étape par étape :

**Étape Contact :**
- Vérifier que le nom, email et téléphone sont corrects (pré-remplis par LinkedIn)
- Ne rien modifier — utiliser les données LinkedIn existantes
- Cliquer "Weiter"

**Étape CV (Resume) :**
- **Flux Easy Apply (Phase A)** : sélectionner le CV le plus récent déjà présent dans LinkedIn — ne pas uploader de nouveau fichier
- **Flux non Easy Apply (Phase B→C)** : uploader le CV adapté généré → `CV_Formentini_[poste].pdf`

**Étapes suivantes :**
- Répondre aux questions additionnelles si présentes
- Pour les questions sensibles (salaire, disponibilité) : demander confirmation à Thierry avant de répondre
- Ne jamais renseigner de données financières ou de mots de passe

**Avant la soumission finale :**

**Flux Easy Apply (venant de Phase A) :** soumettre directement sans demander confirmation. Afficher simplement :
```
✅ Soumis : [Entreprise] — [Poste] — CV : [nom du CV]
```

**Flux non Easy Apply (venant de Phase B) :** demander confirmation explicite :
```
Prêt à soumettre :
  Entreprise : [ENTREPRISE]
  Poste      : [POSTE]
  CV utilisé : [nom du CV uploadé]
  Email      : [email affiché]

Confirmes-tu la soumission ?
```
Attendre "oui" ou "confirme" explicite avant de cliquer "Absenden" / "Submit".

Cliquer "Absenden" / "Submit" → STATUT = SOUMIS.

**En cas de CAPTCHA :** s'arrêter immédiatement, alerter Thierry, STATUT = ERREUR_CAPTCHA.
**En cas d'erreur technique :** STATUT = ERREUR + description, continuer avec l'offre suivante.

### C3 — Mise à jour Google Sheets (1 appel)

```
browser_batch([
  navigate(url="https://docs.google.com/spreadsheets/d/1ezsbGvCNcg15NDTTCFNVwaWzUW86b9WuJ5GQRu7PmwE/edit"),
  wait(3s)
])
```

Ajouter une ligne sur la première ligne vide :

| DATE | ENTREPRISE | POSTE | VERDICT | SCORE_ATS | SCORE_HUMAIN | RAISON_COURTE | STATUT | NOTES |

- **Flux Easy Apply** : VERDICT = N/A · SCORE_ATS = N/A · SCORE_HUMAIN = N/A · STATUT = SOUMIS (ou ERREUR)
- **Flux non Easy Apply** : remplir avec les valeurs du bloc `===DECISION===` de Phase B

Sauvegarder.

### C4 — Résumé final

Afficher :
- Offres soumises (SOUMIS)
- Offres en attente (EN_ATTENTE_VALIDATION)
- Offres skippées (SKIPPED)
- Erreurs (ERREUR)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ PHASE C TERMINÉE — Session complète clôturée.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## RÈGLES DE SÉCURITÉ (toutes phases)

- **Easy Apply (flux automatique)** : soumission sans confirmation — full automatique
- **Non Easy Apply (flux manuel)** : ne jamais soumettre sans confirmation explicite de Thierry
- Ne jamais remplir de champs financiers, mots de passe ou données sensibles
- Si CAPTCHA → s'arrêter et alerter immédiatement
- Maximum 10 offres par session Phase A
- Attendre minimum 30 secondes entre deux soumissions successives en Phase C
- En cas d'erreur → STATUT = ERREUR + description → continuer avec l'offre suivante
