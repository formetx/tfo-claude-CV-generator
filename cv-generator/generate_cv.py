from __future__ import annotations
import argparse
import sys
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, KeepTogether,
    PageTemplate, Paragraph, Spacer,
)

# ══════════════════════════════════════════════════════════════
# PALETTE & DIMENSIONS
# ══════════════════════════════════════════════════════════════

DARK_BLUE    = HexColor('#1A2E4A')
MID_BLUE     = HexColor('#2E5B8A')
ACCENT       = HexColor('#E85D26')
MID_GREY     = HexColor('#8E9BAA')
TEXT         = HexColor('#1C1C1C')
WHITE        = colors.white
SIDEBAR_BODY = HexColor('#C8D9EC')
SIDEBAR_HEAD = HexColor('#E0EAF6')

PAGE_W, PAGE_H = A4
HEADER_H    = 28 * mm
LEFT_COL    = 60 * mm
MARGIN_LR   = 10 * mm
MARGIN_T    = 6  * mm
MARGIN_B    = 16 * mm
SIDEBAR_PAD = 5  * mm

CONTENT_X = LEFT_COL + 8 * mm
CONTENT_Y = MARGIN_B
CONTENT_W = PAGE_W - CONTENT_X - MARGIN_LR
CONTENT_H = PAGE_H - HEADER_H - MARGIN_T - MARGIN_B

# Hauteurs réelles mesurées (pts) — voir commentaires en bas du fichier
_H_BULLET_1L  = 11.5   # bullet 1 ligne
_H_BULLET_2L  = 22.0   # bullet 2 lignes (wrap)
_H_SUBH       = 15.0   # sous-titre de section
_H_JOB_HEADER = 35.0   # comp + title + date
_H_SECTION_H  = 30.5   # hr + R_SEC (avec spaceBefore/After)
_H_SPACER_JOB = 8.5    # Spacer(1, 3mm) après chaque poste

TARGET_PAGES    = 2
MIN_BULLETS_PER_JOB = 1   # jamais en dessous
FILL_THRESHOLD  = 0.94    # page 2 considérée "remplie" si ≥ 94% utilisés

# ══════════════════════════════════════════════════════════════
# STYLES
# ══════════════════════════════════════════════════════════════

def _st(name: str, **kw) -> ParagraphStyle:
    return ParagraphStyle(name, **kw)

R_SEC  = _st('R_SEC',  fontName='Helvetica-Bold',    fontSize=10,  textColor=DARK_BLUE, leading=13, spaceBefore=10, spaceAfter=2)
R_COMP = _st('R_COMP', fontName='Helvetica-Bold',    fontSize=9,   textColor=DARK_BLUE, leading=12)
R_TITL = _st('R_TITL', fontName='Helvetica-Oblique', fontSize=8,   textColor=MID_BLUE,  leading=11)
R_DATE = _st('R_DATE', fontName='Helvetica',          fontSize=7.5, textColor=MID_GREY,  leading=10, spaceAfter=2)
R_SUBH = _st('R_SUBH', fontName='Helvetica-Bold',    fontSize=8,   textColor=DARK_BLUE, leading=10, spaceBefore=4, spaceAfter=1)
R_BUL  = _st('R_BUL',  fontName='Helvetica',          fontSize=8,   textColor=TEXT,      leading=10.5, leftIndent=8, spaceAfter=1)

# ══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════════════════════════════

@dataclass
class BulletItem:
    text: str
    priority: int = 1   # 1=must-keep, 2=important, 3=nice-to-have

@dataclass
class JobSection:
    subhead: Optional[str]
    bullets: list[BulletItem]

@dataclass
class JobEntry:
    company: str
    title: str
    date: str
    sections: list[JobSection]

@dataclass
class CVData:
    tagline: str
    profile: list[str]          # sidebar profile lines
    expertise: list[str]        # sidebar AI/expertise items
    competencies: list[str]     # sidebar competency items
    jobs: list[JobEntry]
    education: list[tuple]      # (degree, school, year[, detail_lines])  — sidebar
                                # detail_lines est une liste optionnelle de str (spécialités, modules clés)
    footer_right: str = 'Nur relevante Erfahrungen zusammengefasst \u2014 vollst\xe4ndiger Lebenslauf auf Anfrage.'

# ══════════════════════════════════════════════════════════════
# AUTO-CALIBRATION
# ══════════════════════════════════════════════════════════════

def _measure_flowable(f) -> float:
    """Hauteur réelle d'un flowable ReportLab en pts (wrap + spaceBefore + spaceAfter)."""
    w, h = f.wrap(CONTENT_W, 99999)
    sb = getattr(getattr(f, 'style', None), 'spaceBefore', 0) or 0
    sa = getattr(getattr(f, 'style', None), 'spaceAfter',  0) or 0
    return h + sb + sa

def _estimate_height(data: CVData) -> float:
    """
    Mesure la hauteur RÉELLE du contenu en pts en appelant wrap() sur chaque
    flowable — bullets longs (2 lignes) correctement comptés.
    """
    total = 0.0
    # Section header
    for f in (_hr_right(), Paragraph('BERUFSERFAHRUNG', R_SEC)):
        total += _measure_flowable(f)
    for job in data.jobs:
        # Job header
        for cls, style in [(job.company, R_COMP), (job.title, R_TITL), (job.date, R_DATE)]:
            total += _measure_flowable(Paragraph(cls, style))
        for sec in job.sections:
            if sec.subhead:
                total += _measure_flowable(Paragraph(sec.subhead, R_SUBH))
            for b in sec.bullets:
                total += _measure_flowable(Paragraph(f'\u2022\u2002{b.text}', R_BUL))
        total += _H_SPACER_JOB
    return total

FILL_MIN = 0.90   # plancher : jamais en dessous de 90 % de la surface disponible

def auto_calibrate(data: CVData, target_pages: int = TARGET_PAGES) -> CVData:
    """
    Ajuste le contenu pour tenir en `target_pages` pages ET remplir ≥ FILL_MIN.

    Passe A — retrait (si trop long) :
      Supprime les bullets p=3 puis p=2, de la fin vers le début,
      en s'arrêtant dès que le contenu tient. Jamais en dessous de
      MIN_BULLETS_PER_JOB bullets par poste.

    Passe B — remplissage (si trop court) :
      Réintroduit les bullets supprimés (p=3 puis p=2), de la fin vers le
      début, tant que le remplissage est < FILL_MIN ET que le contenu reste
      ≤ available. S'appuie sur _FULL_BULLETS — snapshot des bullets complets
      de chaque poste avant toute suppression — pour savoir quoi réinjecter.

    Retourne une copie profonde de CVData ajustée.
    """
    data = deepcopy(data)
    available = target_pages * CONTENT_H
    floor    = available * FILL_MIN

    # ── Snapshot des bullets complets avant toute suppression ──────
    # Structure : { (company, title) : { section_subhead : [BulletItem, ...] } }
    full_bullets: dict = {}
    for job in data.jobs:
        key = (job.company, job.title)
        full_bullets[key] = {}
        for sec in job.sections:
            full_bullets[key][sec.subhead] = list(sec.bullets)

    def current_height():
        return _estimate_height(data)

    # ── PASSE A : retrait si trop long ─────────────────────────────
    for priority in (3, 2):
        if current_height() <= available:
            break
        for job in reversed(data.jobs):
            for sec in job.sections:
                removable = [b for b in sec.bullets if b.priority >= priority]
                total_bullets = sum(len(s.bullets) for s in job.sections)
                for b in reversed(removable):
                    if total_bullets <= MIN_BULLETS_PER_JOB:
                        break
                    sec.bullets.remove(b)
                    total_bullets -= 1
                    if current_height() <= available:
                        break
                if current_height() <= available:
                    break
            if current_height() <= available:
                break

    # ── PASSE B : remplissage si trop court ────────────────────────
    # On réinjecte les bullets manquants (p=3 d'abord, puis p=2)
    # en partant de la fin des jobs, un bullet à la fois.
    for priority in (3, 2):
        if current_height() >= floor:
            break
        for job in reversed(data.jobs):
            key = (job.company, job.title)
            for sec in job.sections:
                # bullets complets de cette section selon snapshot
                full = full_bullets.get(key, {}).get(sec.subhead, [])
                # bullets déjà présents (textes)
                present = {b.text for b in sec.bullets}
                # candidats à réinjection : même priorité, pas encore présents
                candidates = [b for b in full
                              if b.priority == priority and b.text not in present]
                for b in candidates:
                    if current_height() >= floor:
                        break
                    # tester si l'ajout reste dans la limite
                    sec.bullets.append(b)
                    if current_height() > available:
                        sec.bullets.pop()   # dépasse → annuler
                        break
                if current_height() >= floor:
                    break
            if current_height() >= floor:
                break

    return data

# ══════════════════════════════════════════════════════════════
# FLOWABLE BUILDERS
# ══════════════════════════════════════════════════════════════

def _hr_right() -> HRFlowable:
    return HRFlowable(width='100%', thickness=0.5, color=HexColor('#CDD8E8'),
                      spaceAfter=3, spaceBefore=2)

def _section_header(text: str) -> list:
    return [_hr_right(), Paragraph(text, R_SEC)]

def _build_job(entry: JobEntry) -> list:
    block = [
        Paragraph(entry.company, R_COMP),
        Paragraph(entry.title,   R_TITL),
        Paragraph(entry.date,    R_DATE),
    ]
    for sec in entry.sections:
        if sec.subhead:
            block.append(Paragraph(sec.subhead, R_SUBH))
        for b in sec.bullets:
            block.append(Paragraph(f'\u2022\u2002{b.text}', R_BUL))
    block.append(Spacer(1, 3 * mm))
    # KeepTogether sur le header uniquement (3 lignes) pour éviter orphelins
    flowables = [KeepTogether(block[:3])]
    flowables.extend(block[3:])
    return flowables

def build_content(data: CVData) -> list:
    """Construit la liste de flowables de la colonne droite."""
    s = []
    s.extend(_section_header('BERUFSERFAHRUNG'))
    for job in data.jobs:
        s.extend(_build_job(job))
    # Supprimer le dernier Spacer superflu
    while s and isinstance(s[-1], Spacer):
        s.pop()
    return s

# ══════════════════════════════════════════════════════════════
# SIDEBAR RENDERER
# ══════════════════════════════════════════════════════════════

def make_draw_page(data: CVData):
    """Retourne la fonction onPage pour le PageTemplate."""

    def draw_page(canvas, doc):
        canvas.saveState()

        # Fond sidebar
        canvas.setFillColor(DARK_BLUE)
        canvas.rect(0, 0, LEFT_COL, PAGE_H, fill=1, stroke=0)
        # Header band
        canvas.setFillColor(MID_BLUE)
        canvas.rect(0, PAGE_H - HEADER_H, PAGE_W, HEADER_H, fill=1, stroke=0)
        # Accent stripe
        canvas.setFillColor(ACCENT)
        canvas.rect(0, PAGE_H - 2.5*mm, PAGE_W, 2.5*mm, fill=1, stroke=0)

        # Nom
        canvas.setFont('Helvetica-Bold', 23)
        canvas.setFillColor(WHITE)
        canvas.drawString(LEFT_COL + 8*mm, PAGE_H - 16*mm, 'Thierry Formentini')
        # Tagline
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(HexColor('#BDD0E8'))
        canvas.drawString(LEFT_COL + 8*mm, PAGE_H - 22.5*mm, data.tagline)

        # Sidebar (page 1 uniquement)
        if doc.page == 1:
            x = SIDEBAR_PAD
            w = LEFT_COL - 2 * SIDEBAR_PAD
            y = PAGE_H - HEADER_H - MARGIN_T

            def section(title):
                nonlocal y
                y -= 7
                canvas.setStrokeColor(ACCENT)
                canvas.setLineWidth(0.9)
                canvas.line(x, y, x + w, y)
                y -= 3
                canvas.setFont('Helvetica-Bold', 8.5)
                canvas.setFillColor(HexColor('#E0EAF6'))
                canvas.drawString(x, y - 8, title)
                y -= 19

            def line(text, bold=False, size=7.5, color=None, indent=0):
                nonlocal y
                c = HexColor(color) if isinstance(color, str) else (color or SIDEBAR_BODY)
                canvas.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
                canvas.setFillColor(c)
                canvas.drawString(x + indent, y, text)
                y -= size + 2.5

            # CONTACT
            section('CONTACT')
            line('tfo@syscon.fr', bold=True)
            line('+49 170 44 81 81 4')
            line('Lante 60, D-42281 Wuppertal')
            line('10.12.1970 \u00b7 French')

            # PROFIL
            section('PROFIL')
            for pl in data.profile:
                line(pl, size=7.2)

            # EXPERTISE
            section('EXPERTISE')
            for item in data.expertise:
                line('\u2022  ' + item, size=7.2)

            # COMPÉTENCES
            section('COMP\u00c9TENCES CL\u00c9S')
            for comp in data.competencies:
                line('\u2022  ' + comp, size=7.2)

            # LANGUES
            section('LANGUES')
            for lang, level in [
                ('Fran\xe7ais', 'Langue maternelle'),
                ('Allemand',  'Courant (C1)'),
                ('Anglais',   'Courant (C1)'),
                ('Italien',   'Notions'),
                ('Espagnol',  'Notions'),
            ]:
                canvas.setFont('Helvetica-Bold', 7.5)
                canvas.setFillColor(SIDEBAR_HEAD)
                canvas.drawString(x, y, lang)
                canvas.setFont('Helvetica', 7.2)
                canvas.setFillColor(SIDEBAR_BODY)
                canvas.drawString(x + 28*mm, y, level)
                y -= 10

            # FORMATION
            section('FORMATION')
            for deg, school, year, *details in data.education:
                canvas.setFont('Helvetica-Bold', 7.3)
                canvas.setFillColor(SIDEBAR_HEAD)
                canvas.drawString(x, y, deg)
                y -= 9.5
                canvas.setFont('Helvetica', 7.0)
                canvas.setFillColor(SIDEBAR_BODY)
                canvas.drawString(x, y, f'{school} \u00b7 {year}')
                y -= 9.5
                # Lignes de détail optionnelles (spécialités, modules clés)
                for detail_line in (details[0] if details else []):
                    canvas.setFont('Helvetica', 6.8)
                    canvas.setFillColor(HexColor('#A8BDD4'))
                    canvas.drawString(x + 2, y, detail_line)
                    y -= 8.5
                y -= 3

        # Footer
        canvas.setStrokeColor(HexColor('#CDD8E8'))
        canvas.setLineWidth(0.4)
        canvas.line(20*mm, 12*mm, PAGE_W - 20*mm, 12*mm)
        canvas.setFont('Helvetica', 6.5)
        canvas.setFillColor(MID_GREY)
        canvas.drawString(20*mm, 8*mm,
            'Thierry Formentini  \u00b7  tfo@syscon.fr  \u00b7  +49 170 44 81 81 4')
        canvas.drawRightString(PAGE_W - 20*mm, 8*mm, data.footer_right)

        canvas.restoreState()

    return draw_page

# ══════════════════════════════════════════════════════════════
# PDF BUILD
# ══════════════════════════════════════════════════════════════

def build_pdf(data: CVData, output_path: str, calibrate: bool = True) -> str:
    """
    Génère le PDF.
    Si calibrate=True, applique l'auto-calibration avant la génération.
    Retourne le chemin du fichier généré.
    """
    if calibrate:
        data = auto_calibrate(data)

    doc = BaseDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=0, rightMargin=0,
        topMargin=0, bottomMargin=0,
    )
    frame = Frame(
        CONTENT_X, CONTENT_Y, CONTENT_W, CONTENT_H,
        leftPadding=0, rightPadding=0,
        topPadding=0, bottomPadding=0,
        id='right',
    )
    doc.addPageTemplates([
        PageTemplate(id='main', frames=[frame], onPage=make_draw_page(data))
    ])
    doc.build(build_content(data))
    return output_path



# ══════════════════════════════════════════════════════════════
# LETTRE DE MOTIVATION — GÉNÉRATEUR PDF
# ══════════════════════════════════════════════════════════════

@dataclass
class LetterData:
    recipient_name: str       # ex. "Personio — Recruiting Team"
    recipient_addr: list[str] # lignes d'adresse
    subject: str              # objet de la lettre
    body_paragraphs: list[str]# paragraphes du corps (texte brut)
    city_date: str            # ex. "Wuppertal, 2. Mai 2026"
    salutation: str = 'Sehr geehrte Damen und Herren,'
    closing: str = 'Ich freue mich \xfcber die M\xf6glichkeit eines pers\xf6nlichen Gespr\xe4chs.'
    valediction: str = 'Mit freundlichen Gr\xfc\xdfen'

def build_letter_pdf(letter: LetterData, output_path: str) -> str:
    """Génère une lettre de motivation PDF — style cadre dirigeant, aéré et professionnel."""
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.styles import ParagraphStyle

    LM = 25 * mm
    RM = 25 * mm
    W, H = A4
    HEADER_H_L = 30 * mm   # hauteur du bandeau header lettre

    # ── Typographie professionnelle ──────────────────────────────
    # Corps : 10.5 pt, interligne 16 pt = aéré, lisible, cadre dirigeant
    # Destinataire : 9.5 pt, discret
    # Objet : 11 pt bold, accent coloré
    # Signature : 11 pt bold, bleu foncé

    L_RECIP = ParagraphStyle('L_RECIP', fontName='Helvetica',       fontSize=9.5, textColor=TEXT,      leading=14,   spaceAfter=1)
    L_DATE  = ParagraphStyle('L_DATE',  fontName='Helvetica',       fontSize=9,   textColor=MID_GREY,  leading=13,   spaceBefore=8, spaceAfter=14)
    L_SUBJ  = ParagraphStyle('L_SUBJ',  fontName='Helvetica-Bold',  fontSize=11,  textColor=DARK_BLUE, leading=15,   spaceBefore=6, spaceAfter=16)
    L_SAL   = ParagraphStyle('L_SAL',   fontName='Helvetica',       fontSize=10.5,textColor=TEXT,      leading=16,   spaceAfter=12)
    L_BODY  = ParagraphStyle('L_BODY',  fontName='Helvetica',       fontSize=10.5,textColor=TEXT,      leading=16,   spaceAfter=12)
    L_CLOSE = ParagraphStyle('L_CLOSE', fontName='Helvetica',       fontSize=10.5,textColor=TEXT,      leading=16,   spaceBefore=18, spaceAfter=6)
    L_CGEND = ParagraphStyle('L_CGEND', fontName='Helvetica',       fontSize=10.5,textColor=TEXT,      leading=16,   spaceAfter=0)
    L_SIG   = ParagraphStyle('L_SIG',   fontName='Helvetica-Bold',  fontSize=11,  textColor=DARK_BLUE, leading=15,   spaceBefore=28)

    def draw_letter_page(canvas, doc):
        canvas.saveState()
        # Accent stripe top
        canvas.setFillColor(ACCENT)
        canvas.rect(0, H - 2.5*mm, W, 2.5*mm, fill=1, stroke=0)
        # Header band — légèrement plus haut que dans le CV pour donner de l'air
        canvas.setFillColor(DARK_BLUE)
        canvas.rect(0, H - HEADER_H_L, W, HEADER_H_L - 2.5*mm, fill=1, stroke=0)
        # Nom — grand, blanc, ancré à gauche
        canvas.setFont('Helvetica-Bold', 18)
        canvas.setFillColor(WHITE)
        canvas.drawString(LM, H - 18*mm, 'Thierry Formentini')
        # Tagline sous le nom
        canvas.setFont('Helvetica', 8.5)
        canvas.setFillColor(HexColor('#BDD0E8'))
        canvas.drawString(LM, H - 24*mm, 'AI & Digital Transformation Leader  \u00b7  IT Director  \u00b7  Head of IT')
        # Coordonnées à droite, deux lignes
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(HexColor('#BDD0E8'))
        canvas.drawRightString(W - RM, H - 16*mm,
            'tfo@syscon.fr  \u00b7  +49\u202f170\u202f44\u202f81\u202f81\u202f4  \u00b7  Lante 60, D-42281 Wuppertal')
        canvas.drawRightString(W - RM, H - 22*mm, '10.12.1970  \u00b7  Nationalit\xe9 : Fran\xe7aise')
        # Ligne de séparation footer
        canvas.setStrokeColor(HexColor('#CDD8E8'))
        canvas.setLineWidth(0.4)
        canvas.line(LM, 14*mm, W - RM, 14*mm)
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(MID_GREY)
        canvas.drawString(LM, 9*mm,
            'Thierry Formentini  \u00b7  tfo@syscon.fr  \u00b7  +49\u202f170\u202f44\u202f81\u202f81\u202f4  \u00b7  Lante 60, D-42281 Wuppertal')
        canvas.restoreState()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=LM, rightMargin=RM,
        topMargin=HEADER_H_L + 10*mm,   # marge généreuse sous le header
        bottomMargin=22*mm,
    )

    story = []

    # Bloc destinataire
    for line in letter.recipient_addr:
        story.append(Paragraph(line, L_RECIP))

    # Lieu + date
    story.append(Paragraph(letter.city_date, L_DATE))

    # Ligne séparatrice fine
    story.append(HRFlowable(width='100%', thickness=0.5, color=HexColor('#CDD8E8'),
                             spaceBefore=2, spaceAfter=14))

    # Objet
    story.append(Paragraph(letter.subject, L_SUBJ))

    # Salutation
    story.append(Paragraph(letter.salutation, L_SAL))

    # Corps — chaque paragraphe séparé
    for para in letter.body_paragraphs:
        story.append(Paragraph(para, L_BODY))

    # Closing + signature
    story.append(Paragraph(letter.closing, L_CLOSE))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(letter.valediction, L_CGEND))
    story.append(Paragraph('Thierry Formentini', L_SIG))

    doc.build(story, onFirstPage=draw_letter_page, onLaterPages=draw_letter_page)
    return output_path


# ── Helpers construction données ──────────────────────────────
def _B(text: str, priority: int = 1) -> BulletItem:
    return BulletItem(text, priority)

def _S(subhead, bullets) -> JobSection:
    return JobSection(subhead, bullets)
