"""
Builds the SIH 2026 idea-submission deck for FraudLens.

Starts from the official SIH 2026 template (templates/sih2026_template.pptx), keeps the
template chrome - SIH logo, footer bar, slide number, team badge, section title -
and rebuilds every content slide.

Two rules drive the layout:

  1. The screening round is read cold. Nobody presents it. So every block leads
     with a plain-language line, in rupees, hours, districts or officers, and
     puts the technical proof one line below it for the reader who wants it.
  2. Show the thing. Both of the winning decks we were given are roughly half
     screenshots. Evidence that the system exists is worth more than another
     paragraph claiming it does.

Every figure here is produced by impact.py / model/evaluate.py on the held-out
test months of the synthetic world, and carries that disclosure.
"""
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

# Every path is relative to this file, so the script runs from a fresh clone, from any
# working directory, on any machine. Nothing here reads or writes outside the repo.
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "templates" / "sih2026_template.pptx"            # the team's SIH template (chrome only is kept)
OUT = ROOT / "build" / "FraudLens_SIH2026_PixelRex.pptx"      # generated; never overwrites a hand-edited deck
DOCS = ROOT / "docs"                                          # screenshots and charts placed on the slides

# ---------------------------------------------------------------- palette ---
NAVY   = RGBColor(0x1F, 0x38, 0x64)   # template blue - headings
BLUE   = RGBColor(0x2A, 0x78, 0xD6)   # data, matches the charts
CLAY   = RGBColor(0xB8, 0x5C, 0x37)   # accent, matches the dashboard
INK    = RGBColor(0x19, 0x19, 0x17)
SECOND = RGBColor(0x52, 0x51, 0x4E)
MUTED  = RGBColor(0x8A, 0x87, 0x81)
WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
GREEN  = RGBColor(0x0F, 0x6A, 0x33)

SURF   = RGBColor(0xF7, 0xF6, 0xF2)   # card fill
SURF_B = RGBColor(0xEF, 0xED, 0xE6)   # card fill, deeper
LINE   = RGBColor(0xDF, 0xDC, 0xD2)
TINT_B = RGBColor(0xEC, 0xF2, 0xFB)   # blue tint
TINT_C = RGBColor(0xFA, 0xEF, 0xE9)   # clay tint
TINT_G = RGBColor(0xED, 0xF5, 0xEF)   # green tint

FONT = "Calibri"
MONO = "Consolas"

CHROME = {"Image 0", "Shape 0", "Text 1", "Text 2", "Shape 3", "Text 4", "Text 5"}

L0, R1 = 0.45, 12.88          # content margins
CITE_Y = 6.62


# ---------------------------------------------------------------- helpers ---
def clear(slide, keep=CHROME):
    for sh in list(slide.shapes):
        if sh.name not in keep:
            sh._element.getparent().remove(sh._element)


def card(slide, l, t, w, h, fill=SURF, line=LINE, radius=0.04):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                Inches(l), Inches(t), Inches(w), Inches(h))
    sh.adjustments[0] = radius
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(0.75)
    sh.shadow.inherit = False
    sh.text_frame.text = ""
    return sh


def tb(slide, l, t, w, h, runs, size=10, color=INK, bold=False, align=PP_ALIGN.LEFT,
       space=2, anchor=MSO_ANCHOR.TOP, line_spacing=1.0, font=FONT, italic=False):
    """runs: str, or list of paragraphs; a paragraph is a str or a list of
    (text, {overrides}) tuples."""
    box = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.03)
    tf.margin_top = tf.margin_bottom = Inches(0.01)
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space)
        p.line_spacing = line_spacing
        bits = para if isinstance(para, list) else [(para, {})]
        for text, o in bits:
            r = p.add_run()
            r.text = text
            f = r.font
            f.name = o.get("font", font)
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.italic = o.get("italic", italic)
            f.color.rgb = o.get("color", color)
    return box


def heading(slide, l, t, w, text, size=11.5, color=NAVY):
    """An official template section prompt."""
    return tb(slide, l, t, w, 0.26, text, size=size, bold=True, color=color)


def bullets(slide, l, t, w, h, items, size=9.5, color=SECOND, gap=3.5, bullet="▪  "):
    return tb(slide, l, t, w, h,
              [[(bullet, {"color": CLAY, "bold": True}), (it, {})] for it in items],
              size=size, color=color, space=gap, line_spacing=1.02)


def cite(slide, text):
    tb(slide, L0, CITE_Y, R1 - L0, 0.2,
       [[("Sources:  ", {"bold": True, "color": MUTED}), (text, {})]],
       size=7, color=MUTED, italic=True)


def pic(slide, path, l, t, w, caption=None, cap_w=None):
    p = slide.shapes.add_picture(path, Inches(l), Inches(t), width=Inches(w))
    p.line.color.rgb = LINE
    p.line.width = Pt(0.75)
    if caption:
        h = p.height / 914400
        tb(slide, l, t + h + 0.03, cap_w or w, 0.2, caption,
           size=7.5, color=MUTED, italic=True)
    return p


def stat(slide, l, t, w, h, value, label, vcolor=CLAY, vsize=25, fill=SURF, lsize=7.5):
    card(slide, l, t, w, h, fill=fill)
    tb(slide, l + 0.05, t + 0.08, w - 0.1, h * 0.55, value,
       size=vsize, bold=True, color=vcolor, align=PP_ALIGN.CENTER)
    tb(slide, l + 0.05, t + h - 0.42, w - 0.1, 0.38,
       [ln for ln in label.split("\n")],
       size=lsize, color=SECOND, align=PP_ALIGN.CENTER, line_spacing=0.95, space=0)


def chev(slide, l, t, w, h, title, body, fill=TINT_B, tcolor=NAVY):
    card(slide, l, t, w, h, fill=fill, line=LINE)
    tb(slide, l + 0.06, t + 0.04, w - 0.12, 0.2, title,
       size=8.5, bold=True, color=tcolor, align=PP_ALIGN.CENTER)
    tb(slide, l + 0.06, t + 0.22, w - 0.12, max(h - 0.24, 0.18), body,
       size=7.5, color=SECOND, align=PP_ALIGN.CENTER, line_spacing=0.98)


def arrow(slide, l, t, w=0.16, h=0.14, color=CLAY):
    a = slide.shapes.add_shape(MSO_SHAPE.ISOSCELES_TRIANGLE, Inches(l), Inches(t),
                               Inches(w), Inches(h))
    a.rotation = 90
    a.fill.solid()
    a.fill.fore_color.rgb = color
    a.line.fill.background()
    a.shadow.inherit = False
    return a


def table(slide, l, t, w, rows, widths, size=8, head_fill=NAVY, row_h=0.235,
          head_h=0.26, zebra=True):
    """rows[0] is the header. Returns bottom y."""
    total = sum(widths)
    x0 = l
    y = t
    for ci, cw in enumerate(widths):
        cwi = w * cw / total
        c = card(slide, x0, y, cwi, head_h, fill=head_fill, line=head_fill, radius=0.01)
        tb(slide, x0 + 0.05, y + 0.045, cwi - 0.1, head_h, rows[0][ci],
           size=size, bold=True, color=WHITE,
           align=PP_ALIGN.LEFT if ci == 0 else PP_ALIGN.CENTER)
        x0 += cwi
    y += head_h
    for ri, row in enumerate(rows[1:]):
        x0 = l
        fill = SURF if (zebra and ri % 2 == 0) else WHITE
        for ci, cw in enumerate(widths):
            cwi = w * cw / total
            card(slide, x0, y, cwi, row_h, fill=fill, line=LINE, radius=0.01)
            val = row[ci]
            txt, o = (val, {}) if isinstance(val, str) else val
            tb(slide, x0 + 0.05, y + 0.035, cwi - 0.1, row_h, [[(txt, o)]],
               size=o.get("size", size), color=o.get("color", SECOND),
               bold=o.get("bold", False),
               align=PP_ALIGN.LEFT if ci == 0 else PP_ALIGN.CENTER)
            x0 += cwi
        y += row_h
    return y


SYNTH = ("All performance figures are measured on SYNTHETIC data generated by our own "
         "engine, on held-out months the model never saw. They validate the pipeline; "
         "they are not claims of real-world accuracy.")


# ================================================================ slide 1 ---
def slide1(s):
    for sh in list(s.shapes):
        if sh.name == "Text 9":
            tf = sh.text_frame
            tf.paragraphs[0].runs[0].text = (
                "Watch 25 districts out of 724 and you are standing where 72% of the "
                "stolen cash comes out — before the withdrawal happens.")
        if sh.name == "Shape 8":
            sh.fill.solid(); sh.fill.fore_color.rgb = NAVY


# ================================================================ slide 2 ---
def slide2(s):
    clear(s)
    heading(s, L0, 0.94, 9.0, "Proposed Solution (Describe your Idea / Solution / Prototype)")

    card(s, L0, 1.26, R1 - L0, 0.62, fill=TINT_C, line=LINE)
    tb(s, L0 + 0.14, 1.31, R1 - L0 - 0.28, 0.54, [
        [("Stolen money does not vanish.", {"bold": True, "color": INK, "size": 10.5}),
         (" It sits in a chain of borrowed bank accounts for hours — then someone walks "
          "to an ATM in a far-away district and takes it out in cash.", {"size": 10.5})],
        [("Those few hours are the only chance to act. Every system in use today studies "
          "what has already happened. None of them says where the next withdrawal will be.",
          {"size": 9.5, "color": SECOND})],
    ], size=10.5, color=INK, space=1)

    # --- left: how it addresses the problem
    heading(s, L0, 1.98, 3.6, "How it addresses the problem", size=10)
    card(s, L0, 2.24, 3.6, 2.42)
    tb(s, L0 + 0.13, 2.32, 3.34, 0.2, "TODAY", size=8.5, bold=True, color=CLAY)
    bullets(s, L0 + 0.1, 2.54, 3.4, 0.86, [
        "The complaint is filed after the money is already gone",
        "Police and banks chase the trail account by account",
        "The cash is withdrawn before anyone reaches the ATM",
    ], size=8.2, gap=2.5)
    tb(s, L0 + 0.13, 3.44, 3.34, 0.2, "WITH FRAUDLENS", size=8.5, bold=True, color=GREEN)
    bullets(s, L0 + 0.1, 3.66, 3.4, 0.94, [
        "The money is watched while it is still moving",
        "The districts most likely to see a withdrawal in the next 6 hours are named",
        "The alert reaches the right officer or bank before the cash comes out",
    ], size=8.2, gap=2.5)

    # --- middle: the mechanism
    heading(s, 4.22, 1.98, 3.9, "Detailed explanation of the proposed solution", size=10)
    card(s, 4.22, 2.24, 3.9, 2.42, fill=WHITE)
    chev(s, 4.36, 2.36, 3.62, 0.44, "VICTIM", "money stolen · complaint filed",
         fill=SURF_B, tcolor=SECOND)
    arrow(s, 6.09, 2.85)
    card(s, 4.36, 3.04, 3.62, 0.62, fill=NAVY, line=NAVY)
    tb(s, 4.42, 3.09, 3.5, 0.2, "THE MONEY IS STILL MOVING", size=9, bold=True,
       color=WHITE, align=PP_ALIGN.CENTER)
    tb(s, 4.42, 3.28, 3.5, 0.18, "passed between borrowed accounts for hours",
       size=7.5, color=RGBColor(0xC9, 0xD8, 0xEE), align=PP_ALIGN.CENTER)
    tb(s, 4.42, 3.45, 3.5, 0.2, "FraudLens predicts HERE", size=9, bold=True,
       color=RGBColor(0xF5, 0xC2, 0x9B), align=PP_ALIGN.CENTER)
    arrow(s, 6.09, 3.72)
    chev(s, 4.36, 3.91, 3.62, 0.44, "ATM CASH-OUT", "often in another state",
         fill=TINT_C, tcolor=CLAY)
    tb(s, 4.36, 4.40, 3.62, 0.26,
       "A criminal can change the district, the hour and the amount. He cannot take the "
       "cash out without first moving it through accounts.",
       size=7.5, color=SECOND, italic=True, align=PP_ALIGN.CENTER, line_spacing=0.98)

    # --- right: the working prototype
    heading(s, 8.34, 1.98, 4.54, "The working prototype", size=10)
    pic(s, f"{DOCS}/ui_national.png", 8.34, 2.24, 4.54,
        caption="Live console · all 724 districts scored for the next 6-hour window · "
                "ranked watchlist on the left")

    # --- innovation
    heading(s, L0, 4.78, 6.0, "Innovation and uniqueness of the solution", size=10)
    inno = [
        ("We follow the money, not the map",
         "Others study where fraud happened before. We watch where the stolen money is "
         "sitting right now.", TINT_B, NAVY),
        ("We use the waiting time",
         "The hours the cash spends in borrowed accounts are ignored today. That is "
         "exactly the window we predict in.", TINT_G, GREEN),
        ("Every alert has an owner",
         "Money heading to another state becomes a referral to that state's officer — "
         "not a dashboard nobody owns.", TINT_C, CLAY),
        ("It explains itself",
         "Every alert says why the district was flagged, so an officer can judge it "
         "instead of trusting a black box.", SURF_B, SECOND),
    ]
    x = L0
    for title, body, fill, tc in inno:
        card(s, x, 5.02, 3.02, 1.45, fill=fill)
        tb(s, x + 0.12, 5.13, 2.78, 0.38, title, size=9, bold=True, color=tc)
        tb(s, x + 0.12, 5.48, 2.78, 0.92, body, size=8, color=SECOND, line_spacing=1.02)
        x += 3.14

    cite(s, "MHA / I4C, Problem Statement SIH26184 · NCRP and CFCFRMS, as described in "
            "the problem statement · PIB, I4C–RBIH MoU on mule-account intelligence, "
            "12 May 2026 (PRID 2260277)")


# ================================================================ slide 3 ---
def slide3(s):
    clear(s)
    heading(s, L0, 0.94, 9.0, "Methodology and process for implementation")

    stages = [
        ("DATA", "complaints · mule\ntransactions · ATMs"),
        ("CHAIN RECONSTRUCTION", "chain depth · hop count\n· holding time"),
        ("FEATURE PIPELINE", "724 districts × 1,460\nwindows = 1.06 M rows"),
        ("MODEL", "gradient-boosted trees\n+ probability calibration"),
        ("API + DASHBOARD", "FastAPI · React\n· Leaflet risk map"),
        ("ACTION", "3 role views · alerts\n· intelligence report"),
    ]
    x, w, gap = L0, 1.92, 0.155
    for i, (t_, b_) in enumerate(stages):
        fill, tc = (NAVY, WHITE) if i == 3 else (TINT_B, NAVY)
        card(s, x, 1.24, w, 0.78, fill=fill, line=NAVY if i == 3 else LINE)
        tb(s, x + 0.05, 1.3, w - 0.1, 0.24, t_, size=7.8, bold=True, color=tc,
           align=PP_ALIGN.CENTER, line_spacing=0.95)
        tb(s, x + 0.05, 1.56, w - 0.1, 0.42, b_, size=7,
           color=RGBColor(0xC9, 0xD8, 0xEE) if i == 3 else SECOND,
           align=PP_ALIGN.CENTER, line_spacing=0.98)
        if i < 5:
            a = s.shapes.add_shape(MSO_SHAPE.ISOSCELES_TRIANGLE,
                                   Inches(x + w + 0.026), Inches(1.56), Inches(0.1), Inches(0.13))
            a.rotation = 90; a.fill.solid(); a.fill.fore_color.rgb = CLAY
            a.line.fill.background(); a.shadow.inherit = False
        x += w + gap

    card(s, L0, 2.09, R1 - L0, 0.28, fill=TINT_G, line=RGBColor(0xC6, 0xDF, 0xCC))
    tb(s, L0 + 0.12, 2.135, R1 - L0 - 0.24, 0.22, [[
        ("AUTOMATED ANTI-CHEATING TEST — PASSED", {"bold": True, "color": GREEN, "size": 8.5}),
        ("     We train only on the first 10 months and test on the last 2. An automatic "
         "check re-computes every feature to prove the model never saw the future. "
         "It runs on every build.", {"size": 8, "color": SECOND})]], size=8)

    # --- left: technologies, then the dataset every number rests on
    heading(s, L0, 2.52, 6.1, "Technologies to be used", size=10)
    card(s, L0, 2.76, 6.1, 1.06)
    rows = [
        ("Data / ML", "Python 3.11 · pandas · NumPy · NetworkX · LightGBM · scikit-learn"),
        ("Backend", "FastAPI · uvicorn · SQLite · Parquet"),
        ("Frontend", "React (Vite) · Leaflet choropleth over Census-2011 boundaries"),
        ("Hardware", "One ordinary laptop. No cloud, no internet, no API keys."),
    ]
    y = 2.83
    for k, v in rows:
        tb(s, L0 + 0.12, y, 1.02, 0.22, k, size=8.2, bold=True, color=NAVY)
        tb(s, L0 + 1.18, y, 4.8, 0.24, v, size=8.2, color=SECOND, line_spacing=1.0)
        y += 0.245

    heading(s, L0, 3.92, 6.1,
            "The dataset every number in this deck is measured on", size=10)
    card(s, L0, 4.16, 6.1, 1.62, fill=TINT_B)
    tb(s, L0 + 0.12, 4.22, 5.86, 0.2,
       "SYNTHETIC WORLD  ·  12 months, Jan 2025 – Jan 2026  ·  one seed, fully reproducible",
       size=8, bold=True, color=NAVY)
    tb(s, L0 + 0.12, 4.43, 5.86, 0.46, [[
        ("103,071", {"bold": True, "color": INK}), (" complaints across 5 fraud types  ·  ", {}),
        ("14,47,125", {"bold": True, "color": INK}), (" mule-account transfers  ·  ", {}),
        ("2,84,168", {"bold": True, "color": INK}), (" ATM withdrawals  ·  ", {}),
        ("71,896", {"bold": True, "color": INK}), (" accounts  ·  ", {}),
        ("4,543", {"bold": True, "color": INK}), (" ATMs  ·  all ", {}),
        ("724", {"bold": True, "color": INK}), (" districts", {})]],
       size=7.8, color=SECOND, line_spacing=1.04)
    tb(s, L0 + 0.12, 4.90, 5.86, 0.2, [[
        ("Rs 746.6 crore", {"bold": True, "color": CLAY}),
        (" withdrawn across the year, of which ", {}),
        ("Rs 124.4 crore", {"bold": True, "color": CLAY}),
        (" falls in the two held-out test months.", {})]],
       size=7.8, color=SECOND)
    tb(s, L0 + 0.12, 5.13, 5.86, 0.2, "42 ENGINEERED FEATURES IN 8 GROUPS",
       size=8, bold=True, color=NAVY)
    tb(s, L0 + 0.12, 5.33, 5.86, 0.42,
       "static & geography (3) · calendar and holidays (4) · rolling withdrawals in this "
       "district (5) · neighbouring districts (4) · recency & self-excitation (2) · "
       "distance to an active hotspot (2) · nationwide complaints by fraud type (15) · "
       "live mule chains sitting here now (6)",
       size=7.4, color=SECOND, line_spacing=1.02)

    card(s, L0, 5.86, 3.0, 0.66, fill=TINT_G, line=RGBColor(0xC6, 0xDF, 0xCC))
    tb(s, L0 + 0.1, 5.91, 2.8, 0.2, "BUILT AND WORKING", size=8, bold=True, color=GREEN)
    tb(s, L0 + 0.1, 6.10, 2.8, 0.38,
       "data engine · feature pipeline · leakage test · trained + calibrated model · "
       "evaluation vs 2 baselines · API · dashboard · 3 role views · alerts · report",
       size=6.8, color=SECOND, line_spacing=1.0)
    card(s, 3.55, 5.86, 3.0, 0.66, fill=SURF_B)
    tb(s, 3.65, 5.91, 2.8, 0.2, "NOT BUILT YET (declared)", size=8, bold=True, color=SECOND)
    tb(s, 3.65, 6.10, 2.8, 0.38,
       "graph neural net v2 · live streaming · real CFCFRMS / NCRP integration · online "
       "learning · real SMS / email gateways · persisted audit trail · production auth",
       size=6.8, color=SECOND, line_spacing=1.0)

    # --- right: the drill-down as proof
    heading(s, 6.72, 2.52, 6.16, "Every alert explains itself", size=10)
    pic(s, f"{DOCS}/ui_district.png", 6.72, 2.78, 6.16,
        caption="Drill-down for a flagged district: the reasons behind the score, "
                "the money in flight right now, and the action an officer can take.")

    # --- bottom: built vs not built
    cite(s, "LightGBM — Ke et al., NeurIPS 2017 (Microsoft Research) · Census of India 2011, "
            "district population · India district boundaries, Census-2011 based GeoJSON · "
            "CFCFRMS / NCRP workflow as described in Problem Statement SIH26184")


# ================================================================ slide 4 ---
def slide4(s):
    clear(s)
    heading(s, L0, 0.94, 9.0, "Analysis of the feasibility of the idea")

    pic(s, f"{DOCS}/chart_money_coverage.png", L0, 1.22, 5.52)

    card(s, 6.22, 1.22, 6.66, 0.5, fill=NAVY, line=NAVY)
    tb(s, 6.34, 1.27, 6.42, 0.42, [[
        ("No force can watch 724 districts every six hours.", {"color": WHITE, "size": 9.5, "bold": True})],
        [("FraudLens turns that into a ranked list of 25 — 3.5% of the country — that a "
          "control room can actually act on.", {"color": RGBColor(0xC9, 0xD8, 0xEE), "size": 8.3})]],
       size=9, space=1)

    tb(s, 6.22, 1.84, 6.66, 0.2, "Tested on two months the model had never seen",
       size=9, bold=True, color=NAVY)
    y = table(s, 6.22, 2.06, 6.66, [
        ["Watch this many districts", "Share of India", "Cash covered", "vs past-week map"],
        [("Top 10", {"bold": True, "color": INK}), "1.4%",
         ("Rs 50.6 cr", {"bold": True, "color": CLAY}), ("+Rs 15.1 cr", {"color": GREEN, "bold": True})],
        [("Top 25", {"bold": True, "color": INK}), "3.5%",
         ("Rs 89.9 cr", {"bold": True, "color": CLAY}), ("+Rs 5.0 cr", {"color": GREEN, "bold": True})],
        [("Top 50", {"bold": True, "color": INK}), "6.9%",
         ("Rs 110.6 cr", {"bold": True, "color": CLAY}), ("+Rs 19.1 cr", {"color": GREEN, "bold": True})],
    ], widths=[2.3, 1.2, 1.3, 1.5], size=8.2)

    card(s, 6.22, y + 0.08, 6.66, 0.44, fill=TINT_C)
    tb(s, 6.34, y + 0.13, 6.42, 0.36, [[
        ("Same 10 districts. Same 10 teams. ", {"bold": True, "color": INK, "size": 10}),
        ("Rs 15 crore more cash covered.", {"bold": True, "color": CLAY, "size": 10})]],
       size=10, align=PP_ALIGN.CENTER)

    tb(s, 6.22, y + 0.58, 6.66, 0.4,
       "Rs 124.4 crore was withdrawn in total across the test period. A past-week hotspot "
       "map is a fair tool and already catches a lot, so we show it beside us rather than "
       "against a straw man — our gain is sharpest at the top of the list, which is exactly "
       "where the limited teams are.",
       size=7.6, color=SECOND, italic=True, line_spacing=1.02)

    heading(s, L0, 4.44, 11.0,
            "Potential challenges and risks   |   Strategies for overcoming these challenges",
            size=10)
    risks = [
        ("We have no real complaint or bank data",
         "Real trails sit inside I4C and the banks. Our simulator follows the same documented "
         "rules and keeps the same record shape, so a real feed is a data-source swap."),
        ("A model can look clever by peeking at the future",
         "We train on earlier months and test on later ones. An automatic check re-computes "
         "every feature under a strict cut-off and fails the build if anything leaks."),
        ("Criminals change their routes",
         "We watch the one step they cannot skip — moving money through accounts. The model "
         "retrains in about 22 seconds, so it can follow a new corridor."),
        ("False alarms would waste police time",
         "A short ranked list, with a written reason per alert. At the top 10, 88% of the "
         "districts we flag really do see a cash-out."),
        ("Real bank and police data needs permission",
         "Access must be granted officially. Data is already separated by role and enforced "
         "on the server, so each user sees only what they are entitled to."),
        ("Not every fraud ends at an ATM",
         "Cash is still the common exit today. The same approach points at other exit routes "
         "as criminals shift; the prediction unit does not change."),
    ]
    for i, (t_, b_) in enumerate(risks):
        col, row = i % 3, i // 3
        cx = L0 + col * 4.16
        cy = 4.70 + row * 0.98
        card(s, cx, cy, 4.02, 0.92, fill=TINT_C if row == 0 else SURF)
        tb(s, cx + 0.1, cy + 0.05, 3.82, 0.2, t_, size=8, bold=True, color=CLAY,
           line_spacing=1.0)
        tb(s, cx + 0.1, cy + 0.26, 3.82, 0.62, b_, size=7.2, color=SECOND,
           line_spacing=1.0)

    cite(s, "Our own evaluation on held-out synthetic months (docs/metrics.md, "
            "docs/impact.md) · MHA, Rajya Sabha Q1349, 11 Feb 2026 · " + SYNTH)


# ================================================================ slide 5 ---
def slide5(s):
    """Written for the reader most likely to review SIH26184: someone who works
    NCRP / CFCFRMS every day. Their measures are money frozen, the golden hour,
    and inter-state hand-offs - so that is the language here, not ML metrics.

    The case on the left is real in the synthetic world: an actual complaint,
    chain and cash-out from the held-out test months (find_case.py), chosen as
    a typical case rather than the best one.
    """
    clear(s)
    heading(s, L0, 0.94, 9.0, "Potential impact on the target audience")

    nums = [
        ("3.5%", "of India's districts\nis the entire ask", NAVY, SURF),
        ("72%", "of the stolen cash\nsits inside that list", CLAY, TINT_C),
        ("Rs 16 cr", "lost for every hour\nthe response is delayed", CLAY, TINT_C),
        ("2 in 3", "inter-state cash-outs landed\nin a district already flagged", NAVY, SURF),
        ("Zero", "new officers, portals\nor hardware needed", GREEN, TINT_G),
    ]
    x = L0
    for v, l_, c, f in nums:
        stat(s, x, 1.18, 2.42, 0.86, v, l_, vcolor=c, vsize=21, fill=f, lsize=7.2)
        x += 2.5

    # --- left: the incident log
    card(s, L0, 2.14, 6.12, 2.94, fill=WHITE)
    tb(s, L0 + 0.14, 2.20, 5.8, 0.22,
       "A REAL CASE FROM OUR TEST DATA  ·  months the model never saw",
       size=8.5, bold=True, color=NAVY)
    log = [
        ("5 Dec  17:54", "Rs 35,900 stolen by UPI fraud from a victim in ",
         "East Singhbhum, Jharkhand", False),
        ("5 Dec  19:33", "Complaint reported. By now the money is already moving.", "", False),
        ("overnight", "Passed through 4 mule accounts, heading west.", "", False),
        ("6 Dec  06:00", "FraudLens ranks Rewari, Haryana #12 of 724. ",
         "Haryana receives the referral.", True),
        ("6 Dec  08:03", "First withdrawal — in Rewari. ",
         "2 hours after the alert, nearly 1,200 km from the victim.", False),
    ]
    y = 2.50
    for t_, body, strong, hot in log:
        if hot:
            card(s, L0 + 0.08, y - 0.04, 5.96, 0.46, fill=NAVY, line=NAVY, radius=0.08)
        tcol = WHITE if hot else CLAY
        bcol = WHITE if hot else SECOND
        scol = RGBColor(0xF5, 0xC2, 0x9B) if hot else INK
        tb(s, L0 + 0.16, y + 0.03, 1.12, 0.3, t_, size=8.6, bold=True, color=tcol,
           font=MONO)
        tb(s, L0 + 1.30, y + 0.03, 4.66, 0.4, [[
            (body, {"color": bcol}), (strong, {"bold": True, "color": scol})]],
           size=8.4, line_spacing=1.0)
        y += 0.46
    tb(s, L0 + 0.14, 4.82, 5.84, 0.22, [[
        ("One of 7,218 ", {"bold": True, "color": INK}),
        ("inter-state chains in the two test months whose cash-out district FraudLens "
         "had already flagged.", {})]],
       size=7.6, color=SECOND, italic=True)

    # --- right: the cost of delay
    pic(s, f"{DOCS}/chart_deployment_window.png", 6.78, 2.14, 6.10)

    # --- bottom: what changes, for each reader, in their own terms
    heading(s, L0, 5.18, 12.0, "Benefits of the solution  —  for each person who will use it",
            size=10)
    who = [
        ("For I4C", NAVY, TINT_B,
         "The national pattern, and every inter-state chain turned into a referral with a "
         "named owner — not a dashboard nobody owns."),
        ("For State Police", GREEN, TINT_G,
         "A short list for their own state, plus the money arriving from other states "
         "before it is withdrawn."),
        ("For Banks / FIs", CLAY, TINT_C,
         "Only their own exposed ATMs and accounts, with freeze recommendations. No crime "
         "intelligence is shared."),
        ("For the victim", INK, SURF_B,
         "A CFCFRMS freeze only works while the money is still in an account. This is how "
         "it still is."),
    ]
    x = L0
    for title, tc, fill, body in who:
        card(s, x, 5.44, 3.02, 1.08, fill=fill)
        tb(s, x + 0.12, 5.50, 2.78, 0.22, title, size=9.6, bold=True, color=tc)
        tb(s, x + 0.12, 5.76, 2.78, 0.74, body, size=8.4, color=SECOND, line_spacing=1.02)
        x += 3.14

    cite(s, "Case and figures from our held-out synthetic test months (find_case.py, "
            "impact.py) · MHA, Rajya Sabha Q1349, 11 Feb 2026 — Rs 8,189 crore saved across "
            "23.61 lakh CFCFRMS complaints · " + SYNTH)


# ================================================================ slide 6 ---
def slide6(s):
    clear(s)
    heading(s, L0, 0.94, 9.0, "Details / Links of the reference and research work")

    col_w, gap = 4.02, 4.16

    # --- col 1: official sources
    card(s, L0, 1.24, col_w, 3.1, fill=WHITE)
    tb(s, L0 + 0.12, 1.31, 3.78, 0.2, "GOVERNMENT AND OFFICIAL SOURCES",
       size=8.5, bold=True, color=NAVY)
    refs1 = [
        ("MHA / I4C — Problem Statement SIH26184",
         "Smart India Hackathon 2026. NCRP receives ~8,000 complaints a day."),
        ("MHA, Rajya Sabha Q1349, 11 Feb 2026",
         "Rs 8,189 crore saved across 23.61 lakh CFCFRMS complaints to 31 Dec 2025.\n"
         "mha.gov.in/MHA1/Par2017/pdfs/par2026-pdfs/RS11022026/1349.pdf"),
        ("PIB — I4C–RBIH MoU, 12 May 2026",
         "Mule-account intelligence and Suspect Registry identifiers shared for AI-driven "
         "fraud detection, including MuleHunter.AI.\n"
         "pib.gov.in/PressReleasePage.aspx?PRID=2260277"),
        ("PIB — Curbing Cyber Frauds in Digital India, 8 Oct 2025",
         "9.42 lakh SIM cards and 2,63,348 IMEIs linked to fraud blocked by I4C."),
        ("I4C — Samanvaya / Pratibimb, CFMC, helpline 1930",
         "Existing coordination, mapping and joint-action infrastructure."),
    ]
    y = 1.54
    for t_, b_ in refs1:
        tb(s, L0 + 0.12, y, 3.78, 0.2, t_, size=7.8, bold=True, color=CLAY, line_spacing=1.0)
        n = b_.count("\n") + 1 + len(b_) // 88
        tb(s, L0 + 0.12, y + 0.17, 3.78, 0.4, b_, size=7, color=SECOND, line_spacing=1.0)
        y += 0.19 + 0.115 * max(n, 2)

    # --- col 2: data + technical
    x2 = L0 + gap
    card(s, x2, 1.24, col_w, 1.48, fill=WHITE)
    tb(s, x2 + 0.12, 1.31, 3.78, 0.2, "DATA USED IN THE PROTOTYPE",
       size=8.5, bold=True, color=NAVY)
    tb(s, x2 + 0.12, 1.54, 3.78, 1.1, [
        [("Census of India 2011 — ", {"bold": True, "color": CLAY}),
         ("district populations joined to all 724 districts. 130 districts created after "
          "2011 receive a state-median estimate; each state reconciles to its real total.", {})],
        [("India district boundaries — ", {"bold": True, "color": CLAY}),
         ("public Census-2011-based GeoJSON, 724 districts.", {})],
        [("Everything else — ", {"bold": True, "color": CLAY}),
         ("SYNTHETIC, generated by our own engine. No real personal, complaint or "
          "transaction data appears anywhere in this project.", {})],
    ], size=7, color=SECOND, space=2.5, line_spacing=1.0)

    card(s, x2, 2.8, col_w, 1.54, fill=WHITE)
    tb(s, x2 + 0.12, 2.87, 3.78, 0.2, "TECHNICAL AND METHODOLOGICAL",
       size=8.5, bold=True, color=NAVY)
    tb(s, x2 + 0.12, 3.1, 3.78, 1.18, [
        [("LightGBM — ", {"bold": True, "color": CLAY}),
         ("Ke et al., 'LightGBM: A Highly Efficient Gradient Boosting Decision Tree', "
          "NeurIPS 2017 (Microsoft Research).", {})],
        [("Isotonic calibration — ", {"bold": True, "color": CLAY}),
         ("Zadrozny & Elkan, KDD 2002 — turns a model score into a probability an officer "
          "can read as a probability.", {})],
        [("Hit-rate@top-K and PR-AUC — ", {"bold": True, "color": CLAY}),
         ("the standard metrics for rare-event spatio-temporal prediction; plain accuracy "
          "is misleading at a 5% base rate.", {})],
        [("Self-exciting point processes — ", {"bold": True, "color": CLAY}),
         ("hotspot-forecasting literature; informed our self-excitation features.", {})],
    ], size=7, color=SECOND, space=2.5, line_spacing=1.0)

    # --- col 3: how we differ + links
    x3 = L0 + 2 * gap
    card(s, x3, 1.24, col_w, 1.60, fill=TINT_B)
    tb(s, x3 + 0.12, 1.31, 3.78, 0.2, "HOW OUR WORK DIFFERS", size=8.5, bold=True, color=NAVY)
    tb(s, x3 + 0.12, 1.52, 3.78, 1.26,
       "The systems above focus on investigation, mule-account identification, financial "
       "intelligence and response — all of it after the money has moved.\n"
       "FraudLens adds a forward-looking layer answering one question: where is the money "
       "most likely to be withdrawn next?\n"
       "We measured ourselves against a static hotspot list and a past-week heat map rather "
       "than assuming machine learning is automatically better.",
       size=7.3, color=SECOND, line_spacing=1.02)

    card(s, x3, 2.92, col_w, 1.42, fill=SURF)
    tb(s, x3 + 0.12, 2.98, 3.78, 0.2, "PROJECT LINKS", size=8.5, bold=True, color=NAVY)
    tb(s, x3 + 0.12, 3.19, 3.78, 1.1, [
        [("Source code — ", {"bold": True}),
         ("github.com/Nagul-7/Fraudlens", {"color": BLUE})],
        [("Demo video — ", {"bold": True}),
         ("add link", {"color": CLAY, "italic": True})],
        [("Live prototype — ", {"bold": True}),
         ("add link", {"color": CLAY, "italic": True})],
        [("Full results — ", {"bold": True}),
         ("/docs/metrics.md  ·  /docs/impact.md  (in the repository above)", {"color": BLUE})],
        [("Reproducible — ", {"bold": True}),
         ("one seed rebuilds the database, features, model and a byte-identical metrics "
          "file in about 75 seconds", {})],
    ], size=7.2, color=SECOND, space=2.5, line_spacing=1.0)

    # --- future direction, full width
    card(s, L0, 4.44, R1 - L0, 0.86, fill=SURF_B)
    tb(s, L0 + 0.12, 4.51, 12.2, 0.2, "FUTURE DIRECTION", size=8.5, bold=True, color=SECOND)
    tb(s, L0 + 0.12, 4.73, 12.2, 0.52,
       "Spatio-temporal graph neural network to model accounts, districts and transaction "
       "flows directly  ·  near-real-time streaming ingestion  ·  integration with live "
       "CFCFRMS and NCRP workflows, subject to access and governance  ·  online learning "
       "with drift monitoring  ·  category-specific models and detection of channel shift "
       "away from ATM cash-out  ·  persisted alerts with an immutable audit trail",
       size=7.6, color=SECOND, line_spacing=1.04)

    # --- closing
    card(s, L0, 5.42, R1 - L0, 0.82, fill=NAVY, line=NAVY)
    tb(s, L0 + 0.2, 5.5, 12.03, 0.34,
       "Don't wait for the money to disappear before taking action.",
       size=15, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    tb(s, L0 + 0.2, 5.88, 12.03, 0.3,
       "FraudLens turns the gap between theft and cash-out from a blind spot into a "
       "deployment window.   |   All results in this deck are measured on SYNTHETIC data.",
       size=8.5, color=RGBColor(0xC9, 0xD8, 0xEE), align=PP_ALIGN.CENTER)

    cite(s, "All URLs above were resolved and checked on 20 September 2026. Every "
            "performance figure in this deck comes from our own evaluation scripts on "
            "held-out synthetic months and can be reproduced from the repository.")


def main():
    OUT.parent.mkdir(exist_ok=True)
    prs = Presentation(str(SRC))
    for fn, sl in zip((slide1, slide2, slide3, slide4, slide5, slide6), prs.slides):
        fn(sl)
    prs.save(str(OUT))
    print("saved", OUT)


if __name__ == "__main__":
    main()
