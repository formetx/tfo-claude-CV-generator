"""
generate_cv.py — Thierry Formentini — VERSION 4
================================================
Architecture modulaire et paramétrique.
Usage :
    python generate_cv.py                          → CV de base
    python generate_cv.py --job HASCO              → CV adapté HASCO
    python generate_cv.py --output /tmp/mon_cv.pdf → chemin custom

Fonctionnement de l'auto-calibration
-------------------------------------
L'IA construit un CVData avec TOUS les bullets disponibles, classés par
priorité (1=critique, 2=important, 3=secondaire).
L'auto-calibrateur mesure la hauteur réelle de chaque élément ReportLab,
retire les bullets de priorité 3 puis 2 jusqu'à tenir en TARGET_PAGES pages,
en garantissant un minimum de MIN_BULLETS_PER_JOB bullets par poste.
"""

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
    education: list[tuple]      # (degree_short, school, year)  — sidebar
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

def auto_calibrate(data: CVData, target_pages: int = TARGET_PAGES) -> CVData:
    """
    Ajuste le contenu pour tenir en `target_pages` pages.
    Stratégie :
      1. Retirer les bullets priorité 3 des postes non-essentiels (dernier→premier)
      2. Retirer les bullets priorité 2 si nécessaire
      3. S'arrête dès que ça tient — jamais en dessous de MIN_BULLETS_PER_JOB
    Retourne une copie profonde de CVData ajustée.
    """
    data = deepcopy(data)
    available = target_pages * CONTENT_H

    def current_height():
        return _estimate_height(data)

    # Passe 1 : supprimer p3 en partant de la fin
    for priority in (3, 2):
        h = current_height()
        if h <= available:
            break
        for job in reversed(data.jobs):
            for sec in job.sections:
                removable = [b for b in sec.bullets if b.priority >= priority]
                # compter les bullets totaux dans ce poste
                total_bullets = sum(len(s.bullets) for s in job.sections)
                for b in reversed(removable):
                    if total_bullets <= MIN_BULLETS_PER_JOB:
                        break
                    sec.bullets.remove(b)
                    total_bullets -= 1
                    if current_height() <= available:
                        return data
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
            for deg, school, year in data.education:
                canvas.setFont('Helvetica-Bold', 7.3)
                canvas.setFillColor(SIDEBAR_HEAD)
                canvas.drawString(x, y, deg)
                y -= 9.5
                canvas.setFont('Helvetica', 7.0)
                canvas.setFillColor(SIDEBAR_BODY)
                canvas.drawString(x, y, f'{school} \u00b7 {year}')
                y -= 10.5

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
# CV DATA — BASE (toutes les stations, bullets avec priorités)
# ══════════════════════════════════════════════════════════════

def _B(text: str, priority: int = 1) -> BulletItem:
    """Raccourci : BulletItem(text, priority)."""
    return BulletItem(text, priority)

def _S(subhead: Optional[str], bullets: list[BulletItem]) -> JobSection:
    return JobSection(subhead, bullets)


BASE_CV = CVData(
    tagline='AI & Digital Transformation Leader  \u00b7  Head of IT  \u00b7  CoE AI Builder',

    profile=[
        'Senior AI & tech executive,',
        '3+ ans livrables AI en prod.',
        'Medical imaging, workflow',
        'automation, knowledge AI.',
        'Fort\xe9 : strat\xe9gie + delivery',
        'hands-on + leadership.',
    ],

    expertise=[
        'AI strategy & governance',
        'AI solution design & deployment',
        'Model lifecycle supervision',
        'AI in regulated environments',
        'Data architecture & cloud',
        'Business case for AI',
        'Prompt engineering & agents',
    ],

    competencies=[
        'IT & Digital Transformation',
        'Team Leadership & Change Mgmt',
        'IT Governance (ITIL)',
        'Post-Merger Integration',
        'Cloud & Cybersecurity (NIS2)',
        'CRM/ERP (SAP, Veeva, SFDC)',
        'Business Analytics (Power BI)',
        'Python, JS, SQL, GitHub',
    ],

    education=[
        ('AI Executive Prog.', 'Polytechnique Paris (X)', '2024\u20132025'),
        ('MBA ISA',            'HEC Paris',               '1995'),
        ('Dipl. Ing. Inf./AI', 'UTC Compi\xe8gne',            '1988\u20131993'),
    ],

    jobs=[

        JobEntry(
            company='RADPRAX RADIOLOGY GROUP \u2013 Wuppertal',
            title='Head of IT',
            date='03/2022 \u2013 heute',
            sections=[
                _S('AI Leadership & Delivery', [
                    _B('Strat\xe9gie AI d\xe9finie et ex\xe9cut\xe9e : advisor Board sur risques cyber & digitaux.', 1),
                    _B('Solutions d\u2019imagerie m\xe9dicale AI d\xe9ploy\xe9es : r\xe9duction temps de scan de 50 %.', 1),
                    _B('Automatisation de 60 % des workflows diagnostics via analyse AI.', 1),
                    _B('Assistant IA de connaissances SOP d\xe9ploy\xe9 pour le personnel clinique.', 2),
                    _B('Agents r\xe9ponse AI op\xe9rationnels : helpdesk IT et customer care.', 2),
                    _B('Processus AI int\xe9gr\xe9s dans 30 cliniques.', 3),
                    _B('Architecture donn\xe9es m\xe9dicales con\xe7ue pour supporter les workloads AI en production.', 3),
                ]),
                _S('IT Management', [
                    _B('Roadmap IT strat\xe9gique 3 ans con\xe7ue et ex\xe9cut\xe9e.', 1),
                    _B('Migration cloud (Ionos, Equinix) en environnement 0-trust, conformit\xe9 m\xe9dicale.', 1),
                    _B('Politiques cybers\xe9curit\xe9 globales con\xe7ues ; conformit\xe9 NIS2 impl\xe9ment\xe9e.', 1),
                    _B('Application cloud OTRS : centralisation des tests de conformit\xe9 sur 200 postes r\xe9gul\xe9s.', 2),
                    _B('PMO et gouvernance IT \xe9tablis (ITIL) : incidents, helpdesk, gestion de projets.', 2),
                    _B('Syst\xe8mes t\xe9l\xe9phonie IP (3CX), CRM, Citrix, VMware, HyperV int\xe9gr\xe9s.', 3),
                ]),
            ],
        ),

        JobEntry(
            company='FRESENIUS NEPHROCARE AG \u2013 Frankfurt',
            title='Gesch\xe4ftsf\xfchrer E.T. Software GmbH \u2013 Group IT Director Nephrocare',
            date='06/2015 \u2013 02/2022',
            sections=[
                _S('CEO E.T. Software Developments GmbH', [
                    _B('Int\xe9gration post-fusion men\xe9e ; taille de l\u2019entreprise doubl\xe9e, part de march\xe9 +20 %.', 1),
                    _B('Gouvernance du d\xe9veloppement logiciel optimis\xe9e pour soutenir la croissance.', 2),
                    _B('Plan strat\xe9gique d\xe9fini et ex\xe9cut\xe9 ; confiance march\xe9 restaur\xe9e.', 3),
                ]),
                _S('Group IT Director Nephrocare', [
                    _B('Infrastructure IT centralis\xe9e sur 120 cliniques en Allemagne.', 1),
                    _B('Division IT cr\xe9\xe9e : planification strat\xe9gique, recrutement, budgets, gouvernance, s\xe9curit\xe9.', 1),
                    _B('Syst\xe8mes moderni\xe9s : WAN haute vitesse, VoIP unifi\xe9, helpdesk 24/7.', 2),
                    _B('Risk assessment IT, pr\xe9paration aux audits et conformit\xe9 SOX/EU.', 2),
                    _B('Portfolio de transformation g\xe9r\xe9 : Workday, MS Dynamics, automatisation achats.', 2),
                    _B('Plateforme reporting & business analytics construite sur MS Dynamics & Power BI.', 3),
                    _B('Office 365 d\xe9ploy\xe9 (Mail, SharePoint, Intranet) ; pr\xe9sence en ligne renforc\xe9e.', 3),
                ]),
            ],
        ),

        JobEntry(
            company='BLUE ANGEL \u2013 Frankfurt',
            title='Fondateur / Business Owner',
            date='12/2017 \u2013 01/2021',
            sections=[
                _S(None, [
                    _B('Technologie wearable AI d\xe9velopp\xe9e pour la pr\xe9diction d\u2019urgences cardiaques.', 1),
                    _B('Syst\xe8me cloud analysant 6 signes vitaux, monitoring 24/7 avec intervention m\xe9dicale.', 2),
                    _B('Prototype vendu \xe0 une multinationale pharma \u2014 German Innovation Award.', 1),
                ]),
            ],
        ),

        JobEntry(
            company='ABBVIE LIFE SCIENCE LABORATORIES \u2013 Frankfurt',
            title='Director Commercial IT Innovation \u2013 Board Member',
            date='01/2012 \u2013 03/2015',
            sections=[
                _S('Member of the Board', [
                    _B('Membre du Board Commercial allemand et du Board IT europ\xe9en (WE, Canada, EMEA).', 1),
                    _B('Liaison IT-Zentrale Chicago ; strat\xe9gie IT Westeuropa, Canada, EMEA.', 3),
                ]),
                _S('S\xe9paration Abbott \u2192 AbbVie', [
                    _B('Scission IT supervis\xe9e : infrastructure physique jusqu\u2019aux applications utilisateurs.', 1),
                    _B('IT-Personal, Service-Portfolios, Helpdesk et End-User-Computing reorganis\xe9s.', 2),
                    _B('Conformit\xe9 en environnements de sant\xe9 r\xe9glement\xe9s : SOX, EU, US, 65.000 directives.', 2),
                    _B('Transformation culturelle conduite pour \xe9tablir AbbVie comme entit\xe9 autonome.', 3),
                ]),
                _S('Programme Omnicanal Europ\xe9en', [
                    _B('CRM/CLM Veeva Salesforce d\xe9ploy\xe9 sur 24 pays en 2 ans, 800 commerciaux.', 1),
                    _B('iPads introduits pour 800 repr\xe9sentants commerciaux (CLM, CRM, documents s\xe9curis\xe9s).', 2),
                    _B('Plateforme analytics & reporting financier Western Europe construite.', 2),
                    _B('Applications mobiles m\xe9dicales con\xe7ues pour 5 domaines th\xe9rapeutiques.', 3),
                    _B('Production workflows pour publication d\u2019informations produits valid\xe9es sur le march\xe9.', 3),
                ]),
            ],
        ),

        JobEntry(
            company='JENOPTIK OPTICAL SYSTEMS \u2013 Jena',
            title='CEO Shared Service Center \u2013 Corporate CTO',
            date='01/2007 \u2013 02/2011  |  Budget : 14 M\u20ac  |  \u00c9quipe : 70+',
            sections=[
                _S(None, [
                    _B('SSC cr\xe9\xe9 comme entit\xe9 juridique : IT, Finance, Achats, RH, Immobilier — 70+ collaborateurs.', 1),
                    _B('\xc9conomies jusqu\u2019\xe0 80 % via optimisation sourcing (achats, IT, RH, immobilier).', 1),
                    _B('Transformation IT globale sur 5 divisions mondiales ; centres de comp\xe9tences cr\xe9\xe9s.', 1),
                    _B('Migration SAP R/3, s\xe9curisation WAN, VoIP global, data centers HA (Citrix/VMware).', 1),
                    _B('Framework cybers\xe9curit\xe9 aux normes cryptographiques militaires.', 2),
                    _B('Due diligence men\xe9e pour acquisitions dans le secteur d\xe9fense.', 2),
                    _B('Centralisation des services distribu\xe9s : r\xe9duction des co\xfbts de 50 %.', 3),
                    _B('Harmonisation et automatisation des processus m\xe9tiers cl\xe9s sur 6 domaines.', 3),
                ]),
            ],
        ),

        JobEntry(
            company='TECHEM ENERGY SERVICES \u2013 Frankfurt',
            title='Director IT International & Digital Business',
            date='10/2004 \u2013 12/2006  |  Budget : 10 M\u20ac  |  \u00c9quipe : 30',
            sections=[
                _S(None, [
                    _B('Rationalisation du paysage IT sur 15 pays et 80 villes en Europe.', 1),
                    _B('D\xe9ploiement SAP international (15 pays) : planification, migration, go-live.', 1),
                    _B('R\xe9duction des co\xfbts IT de 4 M\u20ac en 3 ans.', 1),
                    _B('Contrat strat\xe9gique sign\xe9 avec Gaz De France ; due diligence rachat 280 M\u20ac.', 2),
                    _B('Standardisation de l\u2019infrastructure : hardware, software, processus, services.', 3),
                    _B('3 Mio. EUR de revenus additionnels s\xe9curis\xe9s la premi\xe8re ann\xe9e d\u2019op\xe9ration.', 3),
                ]),
            ],
        ),

        JobEntry(
            company='MCKINSEY & COMPANY \u2013 EU',
            title='Senior Strategic Consultant',
            date='01/2003 \u2013 09/2004',
            sections=[
                _S(None, [
                    _B('Strat\xe9gie prix Telecom Austria : +70 M\u20ac de revenus additionnels sur 3 ans.', 1),
                    _B('Rationalisation post-fusion Deutsche Telekom : 30 000 postes restructur\xe9s.', 1),
                    _B('Programme key-account semiconducteurs : +160 M\u20ac de revenus additionnels.', 2),
                    _B('Strat\xe9gie Benelux Telecom : optimisation portefeuille, +50 M\u20ac additionnels.', 3),
                ]),
            ],
        ),

        JobEntry(
            company='COLT TELECOMMUNICATION \u2013 London',
            title='Enterprise Program Manager',
            date='01/1998 \u2013 12/2002  |  Budget : 17 M\u20ac  |  \u00c9quipe : 80',
            sections=[
                _S(None, [
                    _B('Plateforme e-business europ\xe9enne : 10 000 clients en ligne, \xe9conomies 7 M\u20ac/an.', 1),
                    _B('Scale-up \xe9quipe tech de 2 \xe0 35 ing\xe9nieurs (Paris, London, Frankfurt).', 2),
                    _B('Rationalisation de 7 000 PCs et 9 000 applications sur 22 pays.', 2),
                    _B('R\xe9duction de 40 postes et 5 M\u20ac de co\xfbts sur la p\xe9riode.', 3),
                    _B('Centre d\u2019op\xe9rations europ\xe9en mis en place : service client 24/7.', 3),
                ]),
            ],
        ),

    ],
)


# ══════════════════════════════════════════════════════════════
# CV DATA — VARIANTES PAR OFFRE
# Chaque variante part de BASE_CV et surcharge ce qui change.
# ══════════════════════════════════════════════════════════════

def _make_variant(
    job_key: str,
    tagline: str,
    profile: list[str],
    expertise: list[str],
    competencies: list[str],
    job_overrides: dict,        # {index_dans_BASE_CV.jobs : JobEntry partiel ou complet}
    job_order: list[int],       # ordre des indices de BASE_CV.jobs
) -> CVData:
    """
    Construit un CVData variant.
    job_overrides : dict {idx: JobEntry} — remplace le poste à cet index.
    job_order     : liste d'indices dans BASE_CV.jobs — définit l'ordre et la sélection.
    """
    base = deepcopy(BASE_CV)
    data = deepcopy(base)
    data.tagline      = tagline
    data.profile      = profile
    data.expertise    = expertise
    data.competencies = competencies

    # Appliquer les overrides
    for idx, override in job_overrides.items():
        base.jobs[idx] = override

    # Réordonner selon job_order
    data.jobs = [base.jobs[i] for i in job_order]
    return data


# ── Variante HASCO — Bereichsleitung Finance & IT ──────────────

HASCO_CV = _make_variant(
    job_key='HASCO',
    tagline='Bereichsleiter Finance & IT  \u00b7  SAP & ERP  \u00b7  Mittelstand Leadership',
    profile=[
        'Cadre dirigeant Finance & IT,',
        'exp. Mittelstand industrie.',
        'Direction Finance + IT en SSC,',
        'SAP international, M&A, BPM.',
        'Gouvernance double p\xe9rim\xe8tre',
        '+ delivery op\xe9rationnel.',
    ],
    expertise=[
        'Finance & IT Bereichsleitung',
        'SAP R/3 & ERP rollout (15 pays)',
        'Controlling & Budgetverantwortung',
        'Post-Merger Integration',
        'IT Governance (ITIL, PMO)',
        'Business Process Management',
        'Cloud & Cybersecurity (NIS2)',
    ],
    competencies=[
        'Finance & IT Dual Leadership',
        'Controlling & Budgetsteuerung',
        'SAP / ERP International',
        'Post-Merger Integration',
        'IT Governance (ITIL)',
        'Business Analytics (Power BI)',
        'Cloud & Cybersecurity (NIS2)',
        'Team Leadership 70+ pers.',
    ],
    job_overrides={
        # Jenoptik (index 4) → version enrichie Finance+IT
        4: JobEntry(
            company='JENOPTIK OPTICAL SYSTEMS \u2013 Jena  |  TecDAX  |  Defense, Semiconductor',
            title='Gesch\xe4ftsf\xfchrer Shared Service Center \u2013 Corporate CTO',
            date='01/2007 \u2013 02/2011  |  Budget : 14 M\u20ac  |  \u00c9quipe : 70+',
            sections=[
                _S('Finance, Controlling & Multi-Bereichsleitung', [
                    _B('SSC aufgebaut als eigenst\xe4ndige GmbH : Finance (Controlling & Buchhaltung), IT, Einkauf, HR, Immobilien.', 1),
                    _B('Disziplinarische F\xfchrung von 70+ Mitarbeitenden \xfcber alle Servicebereiche ; Budget 14 Mio. EUR.', 1),
                    _B('Bis zu 80 % Kosteneinsparungen durch Sourcing-Optimierung via Online-Portale.', 1),
                    _B('Zentralisierung und Rationalisierung verteilter Dienste : 50 % Kostensenkung in 3 Jahren.', 2),
                    _B('Due-Diligence-Projekte f\xfcr Akquisitionen im Verteidigungssektor.', 2),
                    _B('Audit-, Compliance- und Sicherheitsverantwortung in Zusammenarbeit mit milit\xe4rischen Beh\xf6rden.', 3),
                ]),
                _S('IT-Strategie & Infrastruktur (Corporate CTO)', [
                    _B('Globale IT-Transformation \xfcber 5 Divisionen ; Kompetenzzentren aufgebaut.', 1),
                    _B('SAP R/3-Migration und Prozessstandardisierung konzernweit durchgef\xfchrt.', 1),
                    _B('Sicheres Hochgeschwindigkeits-WAN, globale VoIP-Telefonie, HA-Rechenzentren (Citrix/VMware).', 2),
                    _B('Cybersecurity-Framework nach milit\xe4rischen Kryptografiestandards entwickelt.', 2),
                ]),
            ],
        ),
        # Nephrocare (index 1) → version enrichie
        1: JobEntry(
            company='FRESENIUS NEPHROCARE AG \u2013 Frankfurt  |  120 Kliniken Deutschland',
            title='Gesch\xe4ftsf\xfchrer E.T. Software GmbH \u2013 Group IT Director Nephrocare',
            date='06/2015 \u2013 02/2022',
            sections=[
                _S('CEO E.T. Software Developments GmbH', [
                    _B('Post-Merger-Integration gef\xfchrt ; Unternehmensgr\xf6\xdfe verdoppelt, Marktanteil +20 %.', 1),
                    _B('Softwareentwicklungs-Governance optimiert ; Entwicklungsprozesse skaliert.', 2),
                ]),
                _S('Group IT Director Nephrocare', [
                    _B('Zentrale IT-Organisation f\xfcr 120 Kliniken in Deutschland aufgebaut und gef\xfchrt.', 1),
                    _B('IT-Division gegr\xfcndet : strategische Planung, Recruiting, Budgetsteuerung, Governance.', 1),
                    _B('Transformationsportfolio gesteuert : Workday, MS Dynamics, Beschaffungsautomatisierung.', 1),
                    _B('IT-Risikoanalyse, Auditbereitschaft und Compliance SOX/EU gef\xfchrt.', 2),
                    _B('Reporting-Plattform und Business-Analytics auf MS Dynamics & Power BI aufgebaut.', 2),
                    _B('WAN, VoIP, 24/7-Helpdesk und Medizinprodukte-Support modernisiert.', 3),
                ]),
            ],
        ),
        # Techem (index 5) → version enrichie avec France business dev
        5: JobEntry(
            company='TECHEM ENERGY SERVICES \u2013 Frankfurt  |  15 L\xe4nder, 80 Standorte',
            title='Director IT International & Digital Business',
            date='10/2004 \u2013 12/2006  |  Budget : 10 M\u20ac  |  \u00c9quipe : 30',
            sections=[
                _S('IT-Rationalisierung & SAP-Rollout Europa', [
                    _B('IT-Landschaft \xfcber 15 L\xe4nder und 80 St\xe4dte rationalisiert ; alle Infrastrukturkomponenten standardisiert.', 1),
                    _B('Internationales SAP-Rollout (15 L\xe4nder) : Planung, Migration, Go-live-Stabilisierung.', 1),
                    _B('Globales IT-Kostenreduktionsprogramm : 4 Mio. EUR Einsparungen in 3 Jahren.', 1),
                    _B('Automatisierte Datenintegrationsplattformen f\xfcr End-to-End-Datenaustausch zwischen ERP-Systemen.', 3),
                ]),
                _S('Gesch\xe4ftsentwicklung Frankreich', [
                    _B('Rahmenvertrag mit Gaz de France abgeschlossen ; 1 Mio. Ger\xe4te in Paris installiert.', 1),
                    _B('Due Diligence f\xfcr Akquisition eines franz\xf6sischen Unternehmens (280 Mio. EUR).', 2),
                    _B('3 Mio. EUR zus\xe4tzliche Ums\xe4tze im ersten Betriebsjahr gesichert.', 3),
                ]),
            ],
        ),
        # Radprax (index 0) → version condensée Finance+IT focus
        0: JobEntry(
            company='RADPRAX RADIOLOGY GROUP \u2013 Wuppertal  |  30 Kliniken NRW',
            title='Head of IT',
            date='03/2022 \u2013 heute',
            sections=[
                _S('IT-F\xfchrung & Governance', [
                    _B('3-Jahres-IT-Roadmap entwickelt und umgesetzt ; PMO und ITIL-basierte Governance etabliert.', 1),
                    _B('Cloud-Migration (Ionos, Equinix) in Zero-Trust-Umgebung mit medizinischer Compliance.', 1),
                    _B('Cybersecurity-Policies und NIS2-Konformit\xe4t implementiert.', 1),
                    _B('OTRS-Cloud-Applikation : Zentralisierung der Compliance-Tests f\xfcr 200 Medizinarbeitspl\xe4tze.', 2),
                    _B('Strategischer Advisor des Boards f\xfcr Cyber- und digitale Risiken.', 2),
                ]),
                _S('AI & Digitalisierung', [
                    _B('KI-gest\xfctzte Bildanalyse deployed : Scanzeit um 50 % reduziert.', 1),
                    _B('Automatisierung von 60 % der Diagnose-Workflows durch KI-Analyse.', 1),
                    _B('KI-Wissensassistent (SOP) f\xfcr klinisches Personal entwickelt und ausgerollt.', 2),
                ]),
            ],
        ),
        # AbbVie (index 3) → version enrichie
        3: JobEntry(
            company='ABBVIE LIFE SCIENCE LABORATORIES \u2013 Frankfurt  |  28.000 Mitarbeiter',
            title='Director Commercial IT Innovation \u2013 Mitglied des Vorstands',
            date='01/2012 \u2013 03/2015',
            sections=[
                _S('Board-Verantwortung', [
                    _B('Mitglied des deutschen kaufm\xe4nnischen Vorstands und des europ\xe4ischen IT-Vorstands (WE, Kanada, EMEA).', 1),
                    _B('Verbindung zur IT-Zentrale Chicago ; IT-Strategie \xfcber Westeuropa, Kanada und EMEA mitgestaltet.', 2),
                ]),
                _S('Unternehmenstrennung Abbott \u2192 AbbVie', [
                    _B('IT-Trennung geleitet : physische Infrastruktur bis hin zu Endbenutzeranwendungen.', 1),
                    _B('Compliance SOX, EU, US \xfcbernommen ; validierte Medizinsoftware, Audit-Readiness.', 2),
                ]),
                _S('Omnichannel & Analytics', [
                    _B('Veeva Salesforce CRM/CLM \xfcber 24 L\xe4nder in 2 Jahren ausgerollt, 800 Vertriebsmitarbeiter.', 1),
                    _B('Globale Reporting- und Finanzanalytik-Plattform f\xfcr Westeuropa aufgebaut.', 2),
                ]),
            ],
        ),
    },
    # Ordre : Jenoptik en tête, puis Nephrocare, Techem, Radprax, AbbVie, McKinsey, Colt, Blue Angel
    job_order=[4, 1, 5, 0, 3, 6, 7, 2],
)

# ── Registre des variantes disponibles ─────────────────────────

VARIANTS: dict[str, CVData] = {
    'BASE':  BASE_CV,
    'HASCO': HASCO_CV,
    # Ajouter ici d'autres variantes : 'EY': EY_CV, etc.
}

# ══════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Génère le CV de Thierry Formentini.')
    parser.add_argument('--job',    default='BASE', choices=list(VARIANTS.keys()),
                        help='Variante de CV à générer (défaut: BASE)')
    parser.add_argument('--output', default=None,
                        help='Chemin de sortie du PDF')
    parser.add_argument('--no-calibrate', action='store_true',
                        help='Désactiver l\'auto-calibration')
    args = parser.parse_args()

    data = VARIANTS[args.job]
    if args.output is None:
        suffix = f'_{args.job}' if args.job != 'BASE' else ''
        args.output = f'/mnt/user-data/outputs/Formentini_CV{suffix}.pdf'

    path = build_pdf(data, args.output, calibrate=not args.no_calibrate)
    print(f'\u2713 PDF : {path}')

    # Vérification page count
    try:
        from pypdf import PdfReader
        r = PdfReader(path)
        n = len(r.pages)
        status = '\u2705' if n == TARGET_PAGES else '\u26a0\ufe0f'
        print(f'{status} Pages : {n} (cible : {TARGET_PAGES})')
    except ImportError:
        pass


if __name__ == '__main__':
    main()
