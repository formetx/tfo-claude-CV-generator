"""
phase_b.py — Orchestrateur Phase B candidature Thierry Formentini
=================================================================
Usage :
    python phase_b.py --job-desc "texte de l'offre"
    python phase_b.py --job-desc-file offre.txt
    python phase_b.py --job-id 4408771625   (LinkedIn jobId — nécessite Chrome)

Sorties :
    /mnt/user-data/outputs/Formentini_CV_[COMPANY].pdf
    /mnt/user-data/outputs/Formentini_Lettre_[COMPANY].pdf

Dépendances :
    generate_cv.py  (moteur PDF — même répertoire)
    cv_reference.md (source de vérité CV — même répertoire)
    pip install anthropic reportlab pypdf
"""

from __future__ import annotations
import argparse
import json
import os
import re
import sys
import textwrap
from pathlib import Path

import anthropic

# ── Import du moteur PDF ───────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from generate_cv import (
    CVData, JobEntry, JobSection, BulletItem, LetterData,
    build_pdf, build_letter_pdf,
)

# ══════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════

MODEL          = 'claude-opus-4-5'
MAX_TOKENS     = 8000
CV_REF_PATH    = Path(__file__).parent / 'cv_reference.md'
OUTPUT_DIR     = Path('/mnt/user-data/outputs')

def get_anthropic_client():
    """Crée le client Anthropic. Cherche la clé dans ANTHROPIC_API_KEY."""
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError(
            "Variable ANTHROPIC_API_KEY manquante.\n"
            "Définir : export ANTHROPIC_API_KEY=sk-ant-..."
        )
    return anthropic.Anthropic(api_key=api_key)

# ══════════════════════════════════════════════════════════════
# PROMPT SYSTÈME LLM
# ══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """\
Tu es un expert senior en recrutement IT. Tu génères des CVData JSON adaptés \
à une offre d'emploi à partir d'un CV de référence.

RÈGLES ABSOLUES :
1. Ne jamais inventer, modifier ou approximer un chiffre, une date, un nom \
d'employeur ou un titre de poste du CV de référence.
2. Tous les textes (bullets, tagline, profil, lettre) doivent être rédigés \
dans la langue de l'offre d'emploi.
3. Chaque bullet doit être défendable à l'oral — aucune exagération.
4. Les priorités (1/2/3) reflètent la pertinence pour CETTE offre :
   - 1 = must-keep pour ce poste (compétence centrale de l'offre)
   - 2 = important mais secondaire
   - 3 = nice-to-have / remplissage — retiré en premier par l'auto-calibration si trop long
5. Inclure TOUS les postes du CV (pas de trou chronologique).
   Les postes peu pertinents ont minimum 2 bullets de priorité 1 ou 2.
6. Les postes les plus pertinents pour l'offre viennent EN PREMIER.
7. RÈGLE DE VOLUME — CRITIQUE : le JSON doit générer ~105–115% du contenu nécessaire
   pour remplir 2 pages A4. L'auto-calibration supprimera les bullets p=3 en excès.
   Cela signifie concrètement :
   - Postes centraux (top 2-3) : 6–8 bullets répartis en 2 sous-sections, dont ≥3 p=3
   - Postes partiellement pertinents : 4–6 bullets dont ≥2 p=3
   - Postes anciens / peu pertinents : 3–4 bullets dont ≥1 p=3
   Si le total de bullets est < 35 pour 7 postes, le volume est insuffisant — en ajouter.

FORMAT DE SORTIE : JSON uniquement, aucun texte autour, schéma exact ci-dessous.

```json
{
  "company_slug": "NOM_COURT_SANS_ESPACES",
  "tagline": "Titre accrocheur en 1 ligne max 90 chars",
  "profile": ["ligne1", "ligne2", "ligne3", "ligne4", "ligne5", "ligne6"],
  "expertise": ["item1", "item2", "item3", "item4", "item5", "item6", "item7"],
  "competencies": ["item1", "item2", "item3", "item4", "item5", "item6", "item7", "item8"],
  "jobs": [
    {
      "company": "NOM ENTREPRISE – Ville  |  contexte court",
      "title": "Titre exact du poste",
      "date": "MM/YYYY – MM/YYYY",
      "sections": [
        {
          "subhead": "Titre de section ou null",
          "bullets": [
            {"text": "Bullet text", "priority": 1}
          ]
        }
      ]
    }
  ],
  "education": [
    {
      "degree": "Titre court du diplôme (≤30 chars)",
      "school": "École · Sigle",
      "year": "YYYY ou YYYY–YYYY",
      "details": [
        "Spécialité ou module clé 1 (≤38 chars)",
        "Spécialité ou module clé 2",
        "Spécialité ou module clé 3"
      ]
    }
  ],
  "letter": {
    "recipient_addr": ["Ligne 1", "Ligne 2", "Ligne 3"],
    "city_date": "Wuppertal, D. Monat YYYY",
    "subject": "Objet de la lettre",
    "body_paragraphs": [
      "Paragraphe 1 (pourquoi ce poste — sobre, construit, pas de slogan)",
      "Paragraphe 2 (faits + métriques Radprax + expériences clés — prose nominale)",
      "Paragraphe 3 (valeur ajoutée spécifique — sans superlatif)"
    ]
  }
}
```

CONTRAINTES education :
- Toujours 3 entrées dans cet ordre : Polytechnique X (AI, 2024–2025) · HEC ISA (MBA, 1995) · UTC Compiègne (Dipl.Ing., 1988–1993)
- degree : titre court mais lisible (ex. "AI Executive Program", "MBA — Business Admin.", "Dipl. Ing. — Informatique & IA")
- school : nom complet court (ex. "École Polytechnique Paris (X)", "HEC Paris · ISA", "UTC Compiègne")
- details : 3–4 lignes décrivant spécialités / modules clés — adaptées à l'offre (mettre en avant les spécialités les plus pertinentes)
- Chaque ligne details ≤ 38 caractères (contrainte d'affichage sidebar)

CONTRAINTES letter :
- Langue = langue de l'offre
- Ton : cadre dirigeant, sobre, pas de langage parlé
- Pas de formules comme "Das ist mein Kernprofil", "Kein Konzept ohne Umsetzung"
- Paragraphes courts, phrases construites, métriques factuelles

CONTRAINTES profile (sidebar) :
- 6 lignes de ~25 chars max chacune
- Résumé du positionnement adapté à l'offre

CONTRAINTES expertise + competencies :
- Termes ATS alignés sur l'offre
- Réordonnés par pertinence décroissante
"""

# ══════════════════════════════════════════════════════════════
# PROMPT UTILISATEUR
# ══════════════════════════════════════════════════════════════

def build_user_prompt(cv_ref: str, job_desc: str) -> str:
    return f"""\
## CV DE RÉFÉRENCE

{cv_ref}

---

## OFFRE D'EMPLOI

{job_desc}

---

Génère le JSON CVData adapté à cette offre selon les instructions système.
"""

# ══════════════════════════════════════════════════════════════
# APPEL LLM
# ══════════════════════════════════════════════════════════════

def call_llm(cv_ref: str, job_desc: str) -> dict:
    """Appelle Claude, retourne le JSON parsé. Retry x1 si JSON invalide."""
    client = get_anthropic_client()

    for attempt in range(2):
        msg = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': build_user_prompt(cv_ref, job_desc)}],
        )
        raw = msg.content[0].text.strip()

        # Extraire le JSON (le LLM peut mettre des ```json ... ```)
        m = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', raw)
        json_str = m.group(1) if m else raw

        try:
            data = json.loads(json_str)
            return data
        except json.JSONDecodeError as e:
            if attempt == 0:
                print(f"  ⚠ JSON invalide (tentative 1) : {e} — retry…")
                continue
            raise RuntimeError(f"LLM a produit un JSON invalide après 2 tentatives : {e}") from e

    raise RuntimeError("Échec inattendu call_llm")


def run_from_json(json_data: dict, output_prefix: str | None = None) -> tuple[str, str]:
    """
    Génère CV PDF + Lettre PDF à partir d'un dict JSON déjà parsé.
    Utilisé quand Claude passe directement le JSON sans appel API supplémentaire.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cv_ref = CV_REF_PATH.read_text(encoding='utf-8')

    anomalies = validate_numbers(cv_ref, json_data)
    if anomalies:
        print(f"⚠ Chiffres à vérifier : {anomalies}")

    cv_data     = json_to_cvdata(json_data)
    letter_data = json_to_letterdata(json_data, json_data['letter'])

    slug = (output_prefix or json_data.get('company_slug', 'COMPANY')).upper()
    cv_path     = str(OUTPUT_DIR / f'Formentini_CV_{slug}.pdf')
    letter_path = str(OUTPUT_DIR / f'Formentini_Lettre_{slug}.pdf')

    print("⟳ Génération CV PDF…")
    build_pdf(cv_data, cv_path)
    print(f"✓ CV : {cv_path}")

    print("⟳ Génération lettre PDF…")
    build_letter_pdf(letter_data, letter_path)
    print(f"✓ Lettre : {letter_path}")

    try:
        from pypdf import PdfReader
        n = len(PdfReader(cv_path).pages)
        flag = '✅' if n == 2 else '⚠️'
        print(f"{flag} Pages CV : {n} (cible : 2)")
    except ImportError:
        pass

    return cv_path, letter_path

# ══════════════════════════════════════════════════════════════
# DÉSÉRIALISATION JSON → CVData + LetterData
# ══════════════════════════════════════════════════════════════

EDUCATION_FIXED = [
    (
        'AI Executive Program',
        'École Polytechnique Paris (X)',
        '2024–2025',
        [
            'Stratégie & gouvernance IA en entreprise',
            'Architecture modèles, MLOps, LLM',
            'Transformation digitale & cas métier',
            'AI ethics & régulation (EU AI Act)',
        ]
    ),
    (
        'MBA — Business Administration',
        'HEC Paris · ISA',
        '1995',
        [
            'Strategic Business Development',
            'Strategic Marketing & Finance',
            'Entrepreneurship & Innovation',
        ]
    ),
    (
        'Dipl. Ing. — Informatique & IA',
        'UTC Compiègne',
        '1988–1993',
        [
            'Informatique, IA, Génie logiciel',
            'Systèmes distribués & bases de données',
            'Modélisation & algorithmes avancés',
        ]
    ),
]

def json_to_cvdata(d: dict) -> CVData:
    jobs = []
    for j in d['jobs']:
        sections = []
        for s in j['sections']:
            bullets = [BulletItem(text=b['text'], priority=b['priority'])
                       for b in s['bullets']]
            sections.append(JobSection(subhead=s.get('subhead'), bullets=bullets))
        jobs.append(JobEntry(
            company=j['company'],
            title=j['title'],
            date=j['date'],
            sections=sections,
        ))

    # Education : utiliser le champ LLM si présent (details adaptés à l'offre),
    # sinon fallback sur EDUCATION_FIXED (formation fixe avec details standards)
    edu_raw = d.get('education')
    if edu_raw and isinstance(edu_raw, list) and len(edu_raw) >= 1:
        education = [
            (e['degree'], e['school'], e['year'], e.get('details', []))
            for e in edu_raw
        ]
    else:
        education = EDUCATION_FIXED

    return CVData(
        tagline=d['tagline'],
        profile=d['profile'],
        expertise=d['expertise'],
        competencies=d['competencies'],
        jobs=jobs,
        education=education,
    )


def _detect_lang(text: str) -> str:
    """Détecte la langue dominante sur la base de mots fréquents (DE/EN/FR)."""
    text_lower = text.lower()
    de = sum(text_lower.count(w) for w in [' die ', ' der ', ' und ', ' für ', ' mit ', ' ich ', ' wir '])
    en = sum(text_lower.count(w) for w in [' the ', ' and ', ' for ', ' with ', ' our ', ' your ', ' have '])
    fr = sum(text_lower.count(w) for w in [' les ', ' des ', ' pour ', ' avec ', ' nous ', ' vous ', ' mon '])
    scores = {'de': de, 'en': en, 'fr': fr}
    return max(scores, key=scores.get)

_LETTER_STRINGS = {
    'de': {
        'salutation':  'Sehr geehrte Damen und Herren,',
        'closing':     'Ich freue mich \xfcber die M\xf6glichkeit eines pers\xf6nlichen Gespr\xe4chs.',
        'valediction': 'Mit freundlichen Gr\xfc\xdfen',
    },
    'en': {
        'salutation':  'Dear Hiring Team,',
        'closing':     'I would welcome the opportunity for a personal conversation.',
        'valediction': 'Kind regards,',
    },
    'fr': {
        'salutation':  'Madame, Monsieur,',
        'closing':     'Je serais ravi\xe9 de pouvoir vous rencontrer pour un entretien.',
        'valediction': 'Cordialement,',
    },
}

def json_to_letterdata(d: dict, letter_d: dict) -> LetterData:
    body = ' '.join(letter_d['body_paragraphs'])
    lang = _detect_lang(body)
    strings = _LETTER_STRINGS.get(lang, _LETTER_STRINGS['de'])
    return LetterData(
        recipient_name=d.get('company_slug', ''),
        recipient_addr=letter_d['recipient_addr'],
        subject=letter_d['subject'],
        body_paragraphs=letter_d['body_paragraphs'],
        city_date=letter_d['city_date'],
        salutation=strings['salutation'],
        closing=strings['closing'],
        valediction=strings['valediction'],
    )


def extract_numbers(text: str) -> set[str]:
    """Extrait les nombres composés (>=2 chiffres non séparés par point/virgule seul)."""
    # On cherche des nombres significatifs : montants, pourcentages, années, comptes
    # Format : 14M, 50%, 120, 10.000 (européen) — on normalise les séparateurs
    normalized = text.replace('.', '').replace(',', '')
    return set(re.findall(r'\b\d{3,}\b', normalized))  # nombres de 3+ chiffres

def validate_numbers(cv_ref: str, json_data: dict) -> list[str]:
    """
    Vérifie que les nombres significatifs (3+ chiffres) dans le JSON
    existent dans le CV de référence. Retourne les anomalies.
    """
    ref_numbers  = extract_numbers(cv_ref)
    json_text    = json.dumps(json_data, ensure_ascii=False)
    json_numbers = extract_numbers(json_text)
    anomalies = sorted(json_numbers - ref_numbers)
    return anomalies

# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def run(job_desc: str, output_prefix: str | None = None) -> tuple[str, str]:
    """
    Génère CV PDF + Lettre PDF à partir d'une description d'offre.
    Retourne (cv_path, letter_path).
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Charger cv_reference.md
    cv_ref = CV_REF_PATH.read_text(encoding='utf-8')
    print("✓ cv_reference.md chargé")

    # 2. Appel LLM
    print(f"⟳ Appel LLM ({MODEL})…")
    data = call_llm(cv_ref, job_desc)
    print("✓ JSON reçu")

    # 3. Validation chiffres
    anomalies = validate_numbers(cv_ref, data)
    if anomalies:
        print(f"⚠ Chiffres potentiellement inventés : {anomalies}")
        print("  → Vérification manuelle recommandée avant soumission")

    # 4. Désérialiser
    cv_data    = json_to_cvdata(data)
    letter_data = json_to_letterdata(data, data['letter'])

    # 5. Nommer les fichiers
    slug = data.get('company_slug', 'COMPANY').upper()
    if output_prefix:
        slug = output_prefix
    cv_path     = str(OUTPUT_DIR / f'Formentini_CV_{slug}.pdf')
    letter_path = str(OUTPUT_DIR / f'Formentini_Lettre_{slug}.pdf')

    # 6. Générer les PDFs
    print("⟳ Génération CV PDF…")
    build_pdf(cv_data, cv_path)
    print(f"✓ CV : {cv_path}")

    print("⟳ Génération lettre PDF…")
    build_letter_pdf(letter_data, letter_path)
    print(f"✓ Lettre : {letter_path}")

    # 7. Vérifier le nombre de pages
    try:
        from pypdf import PdfReader
        n = len(PdfReader(cv_path).pages)
        flag = '✅' if n == 2 else '⚠️'
        print(f"{flag} Pages CV : {n} (cible : 2)")
    except ImportError:
        pass

    return cv_path, letter_path


def main():
    parser = argparse.ArgumentParser(
        description='Phase B — Génère CV + lettre adaptés à une offre d\'emploi'
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--job-desc',      help='Texte de l\'offre (inline)')
    group.add_argument('--job-desc-file', help='Fichier texte contenant l\'offre')
    group.add_argument('--json-file',     help='JSON CVData déjà généré (bypass LLM)')
    parser.add_argument('--output-prefix', default=None,
                        help='Préfixe pour les fichiers de sortie (défaut: company_slug)')
    args = parser.parse_args()

    if args.json_file:
        # Mode bypass : JSON pré-généré, pas d'appel LLM
        json_data = json.loads(Path(args.json_file).read_text(encoding='utf-8'))
        cv_path, letter_path = run_from_json(json_data, args.output_prefix)
    else:
        if args.job_desc_file:
            job_desc = Path(args.job_desc_file).read_text(encoding='utf-8')
        else:
            job_desc = args.job_desc
        cv_path, letter_path = run(job_desc, args.output_prefix)

    print(f"\n{'='*50}")
    print(f"PHASE B TERMINÉE")
    print(f"  CV     : {cv_path}")
    print(f"  Lettre : {letter_path}")
    print(f"{'='*50}")


if __name__ == '__main__':
    main()
