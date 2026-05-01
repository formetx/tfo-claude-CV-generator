"""
CV Thierry Formentini — ReportLab v3
Layout: sidebar drawn on canvas (draw_page), single right Frame for content.
Sidebar: CONTACT first, then sections with orange hr ABOVE title.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame,
    Paragraph, Spacer, HRFlowable, KeepTogether
)

# ── Palette ─────────────────────────────────────────────────
DARK_BLUE  = HexColor('#1A2E4A')
MID_BLUE   = HexColor('#2E5B8A')
ACCENT     = HexColor('#E85D26')
MID_GREY   = HexColor('#8E9BAA')
LIGHT_GREY = HexColor('#F0F4F8')
TEXT       = HexColor('#1C1C1C')
WHITE      = colors.white
SIDEBAR_BODY = HexColor('#C8D9EC')
SIDEBAR_HEAD = HexColor('#E0EAF6')

# ── Dimensions ──────────────────────────────────────────────
PAGE_W, PAGE_H = A4
HEADER_H   = 28 * mm
LEFT_COL   = 60 * mm
MARGIN_LR  = 10 * mm
MARGIN_T   = 6  * mm
MARGIN_B   = 16 * mm
SIDEBAR_PAD = 5 * mm

CONTENT_X = LEFT_COL + 8 * mm
CONTENT_Y = MARGIN_B
CONTENT_W = PAGE_W - CONTENT_X - MARGIN_LR
CONTENT_H = PAGE_H - HEADER_H - MARGIN_T - MARGIN_B

# ── Style factory ────────────────────────────────────────────
def st(name, **kw):
    return ParagraphStyle(name, **kw)

# Right-column styles
R_SEC  = st('R_SEC',  fontName='Helvetica-Bold', fontSize=10,
            textColor=DARK_BLUE, leading=13, spaceBefore=10, spaceAfter=2)
R_COMP = st('R_COMP', fontName='Helvetica-Bold', fontSize=9,
            textColor=DARK_BLUE, leading=12)
R_TITL = st('R_TITL', fontName='Helvetica-Oblique', fontSize=8,
            textColor=MID_BLUE, leading=11)
R_DATE = st('R_DATE', fontName='Helvetica', fontSize=7.5,
            textColor=MID_GREY, leading=10, spaceAfter=2)
R_SUBH = st('R_SUBH', fontName='Helvetica-Bold', fontSize=8,
            textColor=DARK_BLUE, leading=10, spaceBefore=4, spaceAfter=1)
R_BUL  = st('R_BUL',  fontName='Helvetica', fontSize=8,
            textColor=TEXT, leading=10.5, leftIndent=8, firstLineIndent=0,
            spaceAfter=1)

def hr_right():
    return HRFlowable(width='100%', thickness=0.5, color=HexColor('#CDD8E8'),
                      spaceAfter=3, spaceBefore=2)

def bullet(text):
    return Paragraph(f'\u2022\u2002{text}', R_BUL)

def sub(text):
    return Paragraph(text, R_SUBH)

def section_header(text):
    return [
        hr_right(),
        Paragraph(text, R_SEC),
    ]


# ══════════════════════════════════════════════════════════════
# SIDEBAR — drawn on canvas each page
# ══════════════════════════════════════════════════════════════
def draw_page(canvas, doc):
    canvas.saveState()

    # Sidebar background
    canvas.setFillColor(DARK_BLUE)
    canvas.rect(0, 0, LEFT_COL, PAGE_H, fill=1, stroke=0)

    # Header band
    canvas.setFillColor(MID_BLUE)
    canvas.rect(0, PAGE_H - HEADER_H, PAGE_W, HEADER_H, fill=1, stroke=0)

    # Accent stripe top
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H - 2.5*mm, PAGE_W, 2.5*mm, fill=1, stroke=0)

    # Name
    canvas.setFont('Helvetica-Bold', 23)
    canvas.setFillColor(WHITE)
    canvas.drawString(LEFT_COL + 8*mm, PAGE_H - 16*mm, 'Thierry Formentini')

    # Tagline
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(HexColor('#BDD0E8'))
    canvas.drawString(LEFT_COL + 8*mm, PAGE_H - 22.5*mm,
                      'AI & Digital Transformation Leader  \u00b7  Head of IT  \u00b7  CoE AI Builder')

    # ── Sidebar content (only page 1) ──────────────────────
    if doc.page == 1:
        x = SIDEBAR_PAD
        w = LEFT_COL - 2 * SIDEBAR_PAD
        y = PAGE_H - HEADER_H - MARGIN_T

        GAP_BIG  = 7
        GAP_SMALL = 3

        def section(title):
            nonlocal y
            y -= GAP_BIG
            # Orange HR first
            canvas.setStrokeColor(ACCENT)
            canvas.setLineWidth(0.9)
            canvas.line(x, y, x + w, y)
            y -= GAP_SMALL
            # Title below
            canvas.setFont('Helvetica-Bold', 8.5)
            canvas.setFillColor(HexColor('#E0EAF6'))
            canvas.drawString(x, y - 8, title)
            y -= 19  # 13 (titre) + 6 (gap titre → contenu)

        def line(text, bold=False, indent=0, size=7.5, color=None):
            nonlocal y
            if color is None:
                color = SIDEBAR_BODY
            canvas.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
            canvas.setFillColor(HexColor(color) if isinstance(color, str) else color)
            canvas.drawString(x + indent, y, text)
            y -= (size + 2.5)

        # ── CONTACT ──────────────────────────────────────────
        section('CONTACT')
        line('tfo@syscon.fr', bold=True)
        line('+49 170 44 81 81 4')
        line('Lante 60, D-42281 Wuppertal')
        line('10.12.1970 \u00b7 French')

        # ── PROFIL ───────────────────────────────────────────
        section('PROFIL')
        profile_lines = [
            'Senior AI & tech executive,',
            '3+ ans livrables AI en prod.',
            'Medical imaging, workflow',
            'automation, knowledge AI.',
            'Fort\xe9 : strat\xe9gie + delivery',
            'hands-on + leadership.',
        ]
        for pl in profile_lines:
            line(pl, size=7.2)

        # ── AI EXPERTISE ─────────────────────────────────────
        section('AI EXPERTISE')
        ai_items = [
            'AI strategy & governance',
            'AI solution design & deployment',
            'Model lifecycle supervision',
            'AI in regulated environments',
            'Data architecture & cloud',
            'Business case for AI',
            'Prompt engineering & agents',
        ]
        for ai in ai_items:
            line('\u2022  ' + ai, size=7.2)

        # ── KEY COMPETENCIES ─────────────────────────────────
        section('COMP\u00c9TENCES CL\u00c9S')
        comps = [
            'IT & Digital Transformation',
            'Team Leadership & Change Mgmt',
            'IT Governance (ITIL)',
            'Post-Merger Integration',
            'Cloud & Cybersecurity (NIS2)',
            'CRM/ERP (SAP, Veeva, SFDC)',
            'Business Analytics (Power BI)',
            'Python, JS, SQL, GitHub',
        ]
        for c in comps:
            line('\u2022  ' + c, size=7.2)

        # ── LANGUES ──────────────────────────────────────────
        section('LANGUES')
        langs = [
            ('Fran\xe7ais', 'Langue maternelle'),
            ('Allemand',  'Courant (C1)'),
            ('Anglais',   'Courant (C1)'),
            ('Italien',   'Notions'),
            ('Espagnol',  'Notions'),
        ]
        for lang, level in langs:
            canvas.setFont('Helvetica-Bold', 7.5)
            canvas.setFillColor(SIDEBAR_HEAD)
            canvas.drawString(x, y, lang)
            canvas.setFont('Helvetica', 7.2)
            canvas.setFillColor(SIDEBAR_BODY)
            canvas.drawString(x + 28*mm, y, level)
            y -= 10

        # ── FORMATION ────────────────────────────────────────
        section('FORMATION')
        edu = [
            ('AI Executive Prog.', 'Polytechnique Paris (X)', '2024–2025'),
            ('MBA ISA', 'HEC Paris', '1995'),
            ('Dipl. Ing. Inf. / AI', 'UTC Compi\xe8gne', '1988–1993'),
        ]
        for deg, school, year in edu:
            canvas.setFont('Helvetica-Bold', 7.3)
            canvas.setFillColor(SIDEBAR_HEAD)
            canvas.drawString(x, y, deg)
            y -= 9.5
            canvas.setFont('Helvetica', 7.0)
            canvas.setFillColor(SIDEBAR_BODY)
            canvas.drawString(x, y, f'{school} \u00b7 {year}')
            y -= 10.5

    # ── Footer ───────────────────────────────────────────────
    canvas.setStrokeColor(HexColor('#CDD8E8'))
    canvas.setLineWidth(0.4)
    canvas.line(20*mm, 12*mm, PAGE_W - 20*mm, 12*mm)
    canvas.setFont('Helvetica', 6.5)
    canvas.setFillColor(MID_GREY)
    canvas.drawString(20*mm, 8*mm,
        'Thierry Formentini  \u00b7  tfo@syscon.fr  \u00b7  +49 170 44 81 81 4')
    canvas.drawRightString(PAGE_W - 20*mm, 8*mm,
        'Nur relevante Erfahrungen zusammengefasst \u2014 vollst\xe4ndiger Lebenslauf auf Anfrage.')

    canvas.restoreState()


# ══════════════════════════════════════════════════════════════
# RIGHT COLUMN — experience content
# ══════════════════════════════════════════════════════════════
def right_col():
    s = []

    def job(company, title, date, sections):
        """sections = list of (subheading_or_None, [bullet_texts])"""
        block = []
        block.append(Paragraph(company, R_COMP))
        block.append(Paragraph(title, R_TITL))
        block.append(Paragraph(date, R_DATE))
        for subhead, bullets in sections:
            if subhead:
                block.append(sub(subhead))
            for b in bullets:
                block.append(bullet(b))
        block.append(Spacer(1, 3*mm))
        s.append(KeepTogether(block[:4]))  # keep header together
        s.extend(block[4:])

    # EXPÉRIENCE PROFESSIONNELLE
    s.extend(section_header('EXPÉRIENCE PROFESSIONNELLE'))

    job('RADPRAX RADIOLOGY GROUP \u2013 Wuppertal', 'Head of IT', '03/2022 \u2013 aujourd\'hui', [
        ('AI Leadership & Delivery', [
            'Strat\xe9gie AI d\xe9finie et ex\xe9cut\xe9e : advisor Board sur risques cyber & digitaux.',
            'Solutions d\'imagerie m\xe9dicale AI d\xe9ploy\xe9es : r\xe9duction temps de scan de 50 %.',
            'Automatisation de 60 % des workflows diagnostics via analyse AI.',
            'Assistant IA de connaissances SOP d\xe9ploy\xe9 pour le personnel clinique.',
            'Agents r\xe9ponse AI op\xe9rationnels : helpdesk IT et customer care.',
            'Processus AI int\xe9gr\xe9s dans 30 cliniques.',
        ]),
        ('IT Management', [
            'Roadmap IT strat\xe9gique 3 ans con\xe7ue et ex\xe9cut\xe9e (croissance + leadership march\xe9).',
            'Migration cloud (Ionos, Equinix) en environnement 0-trust, conformit\xe9 m\xe9dicale.',
            'Politiques cybers\xe9curit\xe9 globales con\xe7ues ; conformit\xe9 NIS2 impl\xe9ment\xe9e.',
            'Application cloud OTRS : centralisation des tests de conformit\xe9 sur 200 postes r\xe9gul\xe9s.',
            'PMO et gouvernance IT \xe9tablis (ITIL) : incidents, helpdesk, gestion de projets.',
        ]),
    ])

    job('BLUE ANGEL \u2013 Frankfurt', 'Business Owner / Fondateur',
        '12/2017 \u2013 01/2021', [
        (None, [
            'Technologie wearable AI d\xe9velopp\xe9e pour la pr\xe9diction d\'urgences cardiaques.',
            'Syst\xe8me cloud analysant 6 signes vitaux, monitoring 24/7 avec intervention m\xe9dicale.',
            'Prototype vendu \xe0 une multinationale pharma \u2014 r\xe9compens\xe9 par un German Innovation Award.',
        ]),
    ])

    job('FRESENIUS NEPHROCARE AG \u2013 Frankfurt',
        'Managing Director E.T. Software GmbH \u2013 CIO Nephrocare GmbH',
        '06/2015 \u2013 02/2022', [
        ('CEO E.T. Software Developments GmbH', [
            'Int\xe9gration post-fusion men\xe9e ; taille de l\'entreprise doubl\xe9e, part de march\xe9 +20 %.',
            'Gouvernance du d\xe9veloppement logiciel optimis\xe9e pour soutenir la croissance.',
        ]),
        ('Group IT Director Nephrocare', [
            'Infrastructure IT centralis\xe9e sur 120 cliniques en Allemagne.',
            'Division IT cr\xe9\xe9e : planification strat\xe9gique, recrutement, budgets, gouvernance, s\xe9curit\xe9.',
            'Syst\xe8mes moderni\xe9s : WAN haute vitesse, VoIP unifi\xe9, helpdesk 24/7.',
            'Risk assessment IT, pr\xe9paration aux audits et contr\xf4le conformit\xe9 (SOX, EU).',
            'Portfolio de transformation g\xe9r\xe9 (Workday, MS Dynamics, automatisation achats).',
        ]),
    ])

    job('ABBVIE LIFE SCIENCE LABORATORIES \u2013 Frankfurt',
        'Director Commercial IT Innovation \u2013 Board Member',
        '01/2012 \u2013 03/2015', [
        ('Member of the Board', [
            'Membre du Board Commercial allemand et du Board IT europ\xe9en (WE, Canada, EMEA).',
        ]),
        ('S\xe9paration Abbott \u2192 AbbVie', [
            'Scission IT supervis\xe9e : infrastructure physique jusqu\'aux applications utilisateurs.',
            'Transformation culturelle conduite pour \xe9tablir AbbVie comme entit\xe9 autonome.',
        ]),
        ('Programme Omnicanal Europ\xe9en', [
            'CRM/CLM Veeva Salesforce d\xe9ploy\xe9 sur 24 pays en 2 ans.',
            'iPads introduits pour 800 repr\xe9sentants commerciaux (CLM, CRM, documents s\xe9curis\xe9s).',
            'Plateforme analytics & reporting financier Western Europe construite.',
        ]),
    ])

    job('JENOPTIK OPTICAL SYSTEMS \u2013 Jena',
        'CEO Shared Service Center \u2013 Corporate CTO',
        '01/2007 \u2013 02/2011  |  Budget : 14 M\u20ac  |  \u00c9quipe : 70+', [
        (None, [
            '\xc9conomies jusqu\'\xe0 80 % via optimisation sourcing (achats, IT, RH, immobilier).',
            'Transformation IT globale sur 5 divisions mondiales ; centres de comp\xe9tences cr\xe9\xe9s.',
            'Migration SAP R/3, s\xe9curisation WAN, VoIP global, data centers HA (Citrix/VMware).',
            'Framework cybers\xe9curit\xe9 connu aux normes cryptographiques militaires.',
        ]),
    ])

    job('TECHEM ENERGY SERVICES \u2013 Frankfurt',
        'Director IT International & Digital Business',
        '10/2004 \u2013 12/2006  |  Budget : 10 M\u20ac  |  \u00c9quipe : 30', [
        (None, [
            'Rationalisation du paysage IT sur 15 pays et 80 villes en Europe.',
            'D\xe9ploiement SAP international (15 pays) : planification, migration, go-live.',
            'R\xe9duction des co\xfbts IT de 4 M\u20ac en 3 ans.',
            'Contrat strat\xe9gique sign\xe9 avec Gaz De France ; 1 M de devices d\xe9ploy\xe9s \xe0 Paris.',
        ]),
    ])

    job('MCKINSEY & COMPANY \u2013 EU',
        'Senior Strategic Consultant',
        '01/2003 \u2013 09/2004', [
        (None, [
            'Strat\xe9gie prix Telecom Austria : +70 M\u20ac de revenus additionnels sur 3 ans.',
            'Rationalisation post-fusion Deutsche Telekom : 5 entit\xe9s nationales, 30 000 postes restructur\xe9s.',
            'Programme key-account semiconducteurs : +160 M\u20ac de revenus additionnels.',
        ]),
    ])

    job('COLT TELECOMMUNICATION \u2013 London',
        'Enterprise Program Manager',
        '01/1998 \u2013 12/2002  |  Budget : 17 M\u20ac  |  \u00c9quipe : 80', [
        (None, [
            'Plateforme e-business europ\xe9enne : 10 000 clients en ligne, \xe9conomies de 7 M\u20ac/an.',
            'Scale-up \xe9quipe tech de 2 \xe0 35 ing\xe9nieurs (Paris, London, Frankfurt).',
            'Rationalisation de 7 000 PCs et 9 000 applications sur 22 pays.',
        ]),
    ])

    # Remove trailing spacer
    while s and isinstance(s[-1], Spacer):
        s.pop()

    return s


# ══════════════════════════════════════════════════════════════
# BUILD
# ══════════════════════════════════════════════════════════════
OUTPUT = '/mnt/user-data/outputs/Thierry_Formentini_CV.pdf'

doc = BaseDocTemplate(
    OUTPUT,
    pagesize=A4,
    leftMargin=0, rightMargin=0,
    topMargin=0, bottomMargin=0,
)

right_frame = Frame(
    CONTENT_X, CONTENT_Y,
    CONTENT_W, CONTENT_H,
    leftPadding=0, rightPadding=0,
    topPadding=0, bottomPadding=0,
    id='right'
)

doc.addPageTemplates([
    PageTemplate(id='main', frames=[right_frame], onPage=draw_page)
])

doc.build(right_col())
print(f'\u2713 PDF: {OUTPUT}')
