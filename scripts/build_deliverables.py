#!/usr/bin/env python3
"""Build factual PDF and PPTX technical artifacts from generated metrics/screenshots."""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle, PageBreak, Image, KeepTogether)
from reportlab.pdfbase.pdfmetrics import stringWidth
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt
from PIL import Image as PILImage
import cairosvg

results = json.loads((ROOT / "deliverables/evaluation_results.json").read_text(encoding="utf-8"))
image_eval = json.loads((ROOT / "deliverables/image_evaluation_results.json").read_text(encoding="utf-8"))
quality = json.loads((ROOT / "data/processed/data_quality_report.json").read_text(encoding="utf-8"))
screen_workflow = ROOT / "deliverables/screenshots/DawaLink_completed_pharmacy_question.png"
screen_message = ROOT / "deliverables/screenshots/DawaLink_completed_pharmacy_question.png"
for file in (screen_workflow, screen_message):
    if not file.exists():
        raise SystemExit(f"Missing actual application screenshot: {file}")

INK = colors.HexColor("#18312C")
GREEN = colors.HexColor("#477256")
MUTED = colors.HexColor("#64726D")
PAPER = colors.HexColor("#F4F2EA")
ACCENT = colors.HexColor("#D9F36D")
PALE = colors.HexColor("#EFF4E9")
LINE = colors.HexColor("#D9DDD2")
ORANGE = colors.HexColor("#E8B94F")


def fmt_pct(value):
    return f"{value:.1%}" if value is not None else "not measured"


def footer(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(LINE); canvas.line(18 * mm, 15 * mm, width - 18 * mm, 15 * mm)
    canvas.setFont("Helvetica", 8); canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, "DawaLink · local-first medication identification and pharmacy enquiry")
    canvas.drawRightString(width - 18 * mm, 10 * mm, str(doc.page))
    canvas.restoreState()


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleDL", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=26, leading=30, textColor=INK, spaceAfter=8))
styles.add(ParagraphStyle(name="SubtitleDL", parent=styles["Normal"], fontName="Helvetica", fontSize=12, leading=17, textColor=MUTED, spaceAfter=14))
styles.add(ParagraphStyle(name="HeadingDL", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=17, leading=22, textColor=INK, spaceBefore=5, spaceAfter=8))
styles.add(ParagraphStyle(name="SubheadingDL", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=15, textColor=GREEN, spaceBefore=6, spaceAfter=4))
styles.add(ParagraphStyle(name="BodyDL", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.2, leading=13.1, textColor=INK, spaceAfter=6))
styles.add(ParagraphStyle(name="SmallDL", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=10.5, textColor=MUTED, spaceAfter=4))
styles.add(ParagraphStyle(name="CalloutDL", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=9, leading=13, textColor=INK, backColor=PALE, borderColor=GREEN, borderWidth=0, borderPadding=8, spaceBefore=5, spaceAfter=8))
styles.add(ParagraphStyle(name="RefDL", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.8, leading=10.5, textColor=INK, spaceAfter=4, wordWrap="CJK"))


def P(txt, style="BodyDL"):
    return Paragraph(txt, styles[style])


def table(data, widths, header=True):
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8), ("LEADING", (0, 0), (-1, -1), 10),
                ("TEXTCOLOR", (0, 0), (-1, -1), INK), ("GRID", (0, 0), (-1, -1), .35, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    if header:
        commands.extend([("BACKGROUND", (0, 0), (-1, 0), INK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                         ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")])
        if len(data) > 2:
            commands.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAPER]))
    t.setStyle(TableStyle(commands))
    return t


def quality_chart():
    fields = [("EPI", quality["missing_values"]["epi"]), ("Status", quality["missing_values"]["statut"]),
              ("PPV", quality["missing_values"]["ppv"]), ("PH", quality["missing_values"]["ph"])]
    rows = [[P("Missing or unavailable field", "SmallDL"), P("Rows", "SmallDL"), P("Share of 9,908", "SmallDL")]]
    for name, count in fields:
        rows.append([P(name), P(f"{count:,}"), P(fmt_pct(count / quality["source_rows"]))])
    return table(rows, [60 * mm, 30 * mm, 39 * mm])


def make_pdf(path):
    doc = BaseDocTemplate(str(path), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=17 * mm, bottomMargin=21 * mm,
                          title="DawaLink Technical Report", author="DawaLink project")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="normal", frames=frame, onPage=footer)])
    story = []
    story += [Spacer(1, 23 * mm), P("DawaLink", "TitleDL"),
              P("A local-first Moroccan medicine enquiry assistant with conversational AI", "SubtitleDL"),
              P(f"Technical report · {date.today().isoformat()} · repository baseline {__import__('subprocess').run(['git','rev-parse','--short','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()}", "SmallDL"),
              Spacer(1, 5 * mm), P("Implemented scope", "HeadingDL"),
              P("DawaLink guides a customer through a real pharmacy question: describe a stock or price need in Darija, Arabic or French, confirm the matching medicine and exact strength in the local catalogue, then copy a message for a pharmacy. Qwen3 1.7B runs locally through Ollama and extracts intent and details into a constrained schema. SQLite supplies all product facts. Optional image OCR uses Tesseract locally. No hosted AI service or paid API is used.", "BodyDL"),
              P("Observed live integration flow: the Qwen model parsed a Darija stock question with a requested city, returned three 1 G catalogue candidates with correct package sizes, and the selected catalogue ID generated an editable Darija enquiry. A separate Arabic symptom question received the safety response. These are smoke interactions, not a benchmark. A previous core suite had 18 tests pass; the new LLM flow has no representative accuracy evaluation.", "CalloutDL"),
              P("This is a pharmacy enquiry aid, not clinical decision support. It does not diagnose, prescribe, verify stock, find nearby pharmacies, contact an office, or send user text to a cloud service. Prompts go to local Ollama on loopback.", "BodyDL"),
              PageBreak()]

    story += [P("1. Product and architecture", "HeadingDL"),
              P("The user speaks in their own words, and the local Qwen model extracts goal, medicine, strength, form, quantity and city as JSON. A grounding step rejects details not supported by the message. Candidate records are retrieved and ranked from SQLite; strength and stated form conflicts are filtered. For an image, the API validates JPEG/PNG/WebP, applies local preprocessing, runs Tesseract, then searches the same catalogue. A pharmacy enquiry requires the user to select a real catalogue ID.", "BodyDL"),
              P("Runtime flow", "SubheadingDL"),
              table([[P("Browser chat", "SmallDL"), P("Python WSGI API", "SmallDL"), P("Local model + core", "SmallDL"), P("SQLite + FTS5", "SmallDL")],
                     [P("Describe · confirm · copy", "SmallDL"), P("validation · grounded results", "SmallDL"), P("Ollama · Qwen3 1.7B · OCR", "SmallDL"), P("9,908 catalogue records", "SmallDL")]], [40*mm, 43*mm, 52*mm, 39*mm], header=False),
              Spacer(1, 3 * mm), P("Customer story", "SubheadingDL"),
              P("A customer asks in Darija whether a medicine is available in Rabat. The assistant understands the goal, finds three exact 1 G records, and asks the customer to confirm the package. After the choice, the customer selects the question type, edits quantity or city, reviews the message and copies it to contact a pharmacy. Pharmacy inventory, price changes and replies remain with the real pharmacy.", "BodyDL"),
              Spacer(1, 2 * mm), P("Figure 1. Live browser workflow: a Darija request, Qwen interpretation, exact catalogue options, confirmed product, and the message ready for the customer to copy.", "SmallDL")]
    im = Image(str(screen_workflow)); im._restrictSize(174 * mm, 113 * mm); story += [im, PageBreak()]

    story += [P("2. Data source and quality", "HeadingDL"),
              P("The supplied `moroccan_medications.csv` is the only imported dataset. It contains 9,908 rows and ten source columns: id, specialite, substance_active, dosage, forme, presentation, epi, statut, ppv and ph. All IDs are unique; 4,070 distinct brand strings were observed. Source export date was not recorded, and the supplied `ammps_cards.csv` is empty.", "BodyDL"),
              P("Missing/unavailable values are preserved, not imputed. EPI is blank for all rows; status is blank for 1,810; PPV and PH each have 1,098 empty or explicit no-price values. No manufacturer information is recoverable from the all-empty EPI field.", "BodyDL"), quality_chart(),
              Spacer(1, 4 * mm), P("Source investigation", "SubheadingDL"),
              P("The official AMMPS search page was reachable and reported 9,936 entries with an update date of 2026-10-01 during research. The older repository export has 9,908 rows; it is not presented as current or complete. AMMPS bulk reuse terms were not identified, so the application does not scrape or refresh that site.", "BodyDL"),
              P("The Moroccan Open Data portal lists a CNOPS medicines reference under ODbL, but the linked XLSX is from 2014. The portal returned 503 and its old resource host did not resolve in this environment. The dataset is not mixed into current catalogue records because it could not be fetched and its prices/status are stale. The original repository has no explicit data license file; check reuse rights before redistribution.", "BodyDL"),
              P("Normalization stores original text plus deterministic normalized brand/substance keys, source attribution and import timestamp. SQLite rebuild writes a new temporary database and swaps it in after import. FTS5 and indexes support local ranked lookups. `scripts/ingest_data.py` emits a JSON quality report. The raw CSV remains unchanged.", "BodyDL"), PageBreak()]

    story += [P("3. Search and request understanding", "HeadingDL"),
              P("Search combines SQLite FTS5, normalized text, partial matching and Python `SequenceMatcher`. The model extracts product name, strength and form from the conversation, but the application grounds those fields against what the user said and the available catalogue. Explicit strength and form conflicts are filtered. Scores are matching signals, not calibrated probabilities. The user confirms the exact product before an enquiry can be generated.", "BodyDL"),
              P("The conversational endpoint sends the last user turns to Qwen running at `127.0.0.1:11434` and requests schema-constrained JSON. It handles French, Arabic, Darija Latin/Arabizi, code switching, follow-up turns, and asks for a product name when it is missing. User-stated package quantity stays separate from package size in a catalogue record. A high-precision local guard handles obvious symptom and personal-dosing requests; no model answer is allowed to prescribe or invent availability.", "BodyDL"),
              table([[P("Query", "SmallDL"), P("Observed top result", "SmallDL"), P("Top 3 target hit", "SmallDL")],
                     [P("Doliprane 1 G"), P("DOLIPRANE · 1 G"), P("yes")],
                     [P("doliprene"), P("DOLIPRANE · 1 G"), P("yes")],
                     [P("AMOXICILLINE"), P("ALFAMOX · 1 G"), P("yes")],
                     [P("Amlodipine"), P("AM-10 · 10 MG"), P("yes")],
                     [P("DOLIPRANE 500 MG"), P("DOLIPRANE · 500 MG"), P("yes")]], [50*mm, 67*mm, 48*mm]),
              Spacer(1, 4*mm), P("Observed live result · smoke interaction", "SubheadingDL"),
              P('<font name="Courier">Darija: “3afak wach kayn Doliprane 1g f Rabat?”<br/>intent=availability · product=DOLIPRANE · strength=1 G · city=Rabat<br/>3 exact-strength candidates returned; the user selected ID 563 (BOITE DE 8).</font>', "BodyDL"),
              P("If no name can be identified, DawaLink asks for clarification rather than filling a medicine name from generic words like ‘pharmacy’ or ‘children’.", "BodyDL"), PageBreak()]

    story += [P("4. OCR and image matching", "HeadingDL"),
              P("The OCR executable is Tesseract 5.5.0 in the local verification environment; English, French and Arabic trained data were installed. OCR is optional. There is no OCR cloud upload and no vision-language model. Files are capped at 8 MB, checked by file signature and pixel count, preprocessed locally, written to a temporary file and deleted after inference. Text matching uses the same SQLite catalogue.", "BodyDL"),
              P("The automated suite generated a text image and verified that Tesseract read `DOLIPRANE 1 G` and matched actual catalogue records. This proves pipeline wiring, not photograph performance.", "BodyDL"),
              P("Real-image spot check", "SubheadingDL"),
              P("One test image was retrieved from the MIT-licensed Medicine Boxes Annotated dataset (test split). The dataset annotation labels only a generic medicine box; the prominent visible product name DiaCURE was manually transcribed. The product is not the Moroccan D-CURE record. Local OCR extracted ENFANTS / CHILDREN but missed DiaCURE: visible-text CER was 31.8%; product-name read 0/1; Moroccan catalogue top-1/top-3 identification 0/1. The app returned no candidate and required confirmation, avoiding a false D-CURE suggestion. This single foreign-market image is a failure case, not a representative benchmark.", "BodyDL"),
              P("A positive real-photo identification check still needs a photograph of a real product present in the included Moroccan catalogue, with its expected catalogue ID. The image must show a readable brand and strength. This is the only external input needed to close the photo acceptance check.", "CalloutDL"),
              P("Image source: <link href='https://huggingface.co/datasets/gokuljegadeesan/Medicine_boxes_annotated' color='#477256'>Medicine Boxes Annotated</link>, MIT license as listed on dataset card; 874 images, 87.3 MB, one generic object class. The raw image is downloaded only by the optional evaluation script and is not redistributed here.", "SmallDL"), PageBreak()]

    story += [P("5. API, storage and pharmacy workflow", "HeadingDL"),
              table([[P("Endpoint", "SmallDL"), P("Purpose", "SmallDL")],
                     [P("GET /api/health"), P("record count, OCR status, unknown export date")],
                     [P("GET /api/medications?q=…"), P("ranked catalogue search and paging")],
                     [P("GET /api/medications/{id}"), P("one real catalogue record")],
                     [P("POST /api/assistant/message"), P("local LLM dialogue, grounded candidates and next step")],
                     [P("GET /api/assistant/status"), P("Ollama and model availability")],
                     [P("POST /api/interpret"), P("deterministic compatibility parser")],
                     [P("POST /api/recognize"), P("validated multipart image OCR and candidates")],
                     [P("POST /api/pharmacy-request"), P("message from a verified catalogue ID")],
                     [P("GET /api/export"), P("CSV export of search results")]], [62*mm, 103*mm]),
              Spacer(1, 3*mm), P("Database rows preserve the original ten source fields with brand_key, substance_key, source and imported_at; id is the primary key. FTS5 indexes brand, ingredient, dosage, form and presentation. Filter/search SQL is parameterized. Uploaded bytes are not persisted.", "BodyDL"),
              P("The enquiry API refuses a name without a valid local catalogue ID. The UI allows the user to edit dosage, form and package presentation, to select message language, quantity and location, then copy the generated text. Quantity is not confused with package count. No availability is asserted and no message is sent.", "BodyDL"),
              P("Figure 2. Live generated enquiry after product selection. The user sends the message independently.", "SmallDL")]
    im = Image(str(screen_message)); im._restrictSize(174 * mm, 94 * mm); story += [im, PageBreak()]

    story += [P("6. Evaluation and test results", "HeadingDL"),
              P(f"The previously run core automated suite passed 18 tests with local Tesseract configured. Separately, the current LLM route was exercised over HTTP with a Darija availability request, an Arabic symptom question, and a French price question. The full UI workflow was captured from the running app through candidate selection and message copy. The new model route has only smoke coverage; no representative language or entity-accuracy score is claimed.", "BodyDL"),
              P(f"Intent accuracy: {results['intent']['accuracy']:.1%} on {len(results['cases'])} manually authored cases. Language labels: {results['language']['accuracy']:.1%}. Named product extraction: {results['medication_name_extraction']['correct']}/{results['medication_name_extraction']['expected_named_cases']}. Clarification: {results['clarification_decision']['correct']}/{results['clarification_decision']['total']}. Each intent had only 1–6 examples; the set is not representative or independently reviewed, so 100% is only a smoke/evaluation score on these examples.", "BodyDL"),
              table([[P("Evaluation component", "SmallDL"), P("Set size", "SmallDL"), P("Observed result", "SmallDL")],
                     [P("Intent/language rules"), P("16 authored examples"), P("16/16 each; narrow test set")],
                     [P("Catalogue searches"), P("6 authored probes"), P("6/6 top-three hits")],
                     [P("Strength conflict"), P("1 query, top 3"), P("all 3 match 500 mg")],
                     [P("Ambiguous brand"), P("DOLIPRANE top 20"), P("7 strengths; selection required")],
                     [P("Generated-image OCR smoke"), P("1 synthetic image"), P("text read; not photo evidence")],
                     [P("Real-photo OCR"), P("1 foreign product photo"), P("name missed; safe no-match")]], [55*mm, 42*mm, 68*mm]),
              P("Detailed machine-readable results: `evaluation_results.json` and `image_evaluation_results.json`. Full results are reproducible with `scripts/evaluate.py` and `scripts/evaluate_public_ocr.py`.", "BodyDL"), PageBreak()]

    story += [P("7. Reproduction, safety and limitations", "HeadingDL"),
              P("Runtime uses Python standard library and SQLite, plus the separately installed Ollama runtime and one-time Qwen3 1.7B weights for conversation. OCR uses local Tesseract and language packs; optional image preprocessing uses Pillow. Deliverable generation uses the separate pinned requirements file.", "BodyDL"),
              P("Launch from the repository root", "SubheadingDL"),
              P("<font name='Courier'>ollama pull qwen3:1.7b<br/>python3 scripts/ingest_data.py<br/>python3 app.py</font><br/>Start `ollama serve` first if Ollama is not running as a service, then open http://127.0.0.1:8000. Model download is about 1.4 GB and is not bundled.", "BodyDL"),
              P("Verification commands", "SubheadingDL"),
              P("<font name='Courier'>python3 -m unittest discover -s tests -v<br/>python3 scripts/evaluate.py<br/>python3 scripts/evaluate_public_ocr.py</font>", "BodyDL"),
              P("Safety limitations", "SubheadingDL"),
              P("No diagnosis, personal dosing instructions, treatment suggestions, substitutions, interaction checker, pregnancy or child-safety decisions, pharmacy availability integration, pharmacy directory, voice transcription, or external messaging exists. OCR match scores are not probabilities. Confirmation is mandatory for ambiguous results. Catalogue price/status are historic source fields, not live pharmacy data. The local 1.7B model can misunderstand Darija; its parse is constrained and product choices are grounded in the catalogue, but user confirmation remains necessary.", "BodyDL"),
              P("References", "SubheadingDL"),
              P("[1] <link href='https://ammps.gov.ma/recherche-medicaments' color='#477256'>AMMPS official medicine register</link>. [2] <link href='https://www.data.gov.ma/fr/node/14' color='#477256'>Morocco Open Data reuse license (ODbL-derived)</link>. [3] <link href='https://www.data.gov.ma/data/fr/dataset/?groups=sante&amp;license_id=odc-odbl&amp;organization=caisse-nationale-des-organismes-de-prevoyance-sociale&amp;res_format=XLSX&amp;tags=Cnops&amp;tags=m%C3%A9dicament&amp;tags=princeps' color='#477256'>CNOPS medicine reference listing</link>. [4] <link href='https://github.com/tesseract-ocr/tesseract' color='#477256'>Tesseract OCR source</link>. [5] <link href='https://huggingface.co/datasets/gokuljegadeesan/Medicine_boxes_annotated' color='#477256'>Medicine Boxes Annotated dataset</link>. [6] <link href='https://github.com/darija-open-dataset/dataset' color='#477256'>Darija Open Dataset</link> (investigated, not used for pharmacy-intent training). [7] <link href='https://docs.ollama.com/api/chat' color='#477256'>Ollama local chat API</link> and <link href='https://docs.ollama.com/capabilities/structured-outputs' color='#477256'>structured outputs</link>. [8] <link href='https://qwenlm.github.io/blog/qwen3/' color='#477256'>Qwen3 model and Apache 2.0 license</link>.", "RefDL")]
    doc.build(story)


def rgb(hexv):
    s = hexv.lstrip("#")
    return RGBColor(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


PAPER_RGB, INK_RGB, GREEN_RGB, ACCENT_RGB, MUTED_RGB, PALE_RGB = map(rgb, ["#F4F2EA", "#18312C", "#477256", "#D9F36D", "#64726D", "#EFF4E9"])


def add_text(slide, x, y, w, h, text, size=16, color=INK_RGB, bold=False, font="Aptos", align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame; tf.clear(); tf.word_wrap = True
    tf.margin_left = Inches(.03); tf.margin_right = Inches(.03); tf.margin_top = Inches(.02); tf.margin_bottom = Inches(.02)
    for index, line in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if index == 0 else tf.add_paragraph()
        p.text = line; p.alignment = align; p.space_after = Pt(7)
        for run in p.runs:
            run.font.name = font; run.font.size = Pt(size); run.font.bold = bold; run.font.color.rgb = color
    return box


def add_box(slide, x, y, w, h, title, body, fill=PALE_RGB, title_color=GREEN_RGB, body_size=13):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid(); shape.fill.fore_color.rgb = fill; shape.line.color.rgb = rgb("#D9DDD2")
    tf = shape.text_frame; tf.clear(); tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = Inches(.18); tf.margin_right = Inches(.16); tf.margin_top = Inches(.1); tf.margin_bottom = Inches(.08)
    p = tf.paragraphs[0]; p.text = title
    for run in p.runs: run.font.name="Aptos Display"; run.font.size=Pt(18); run.font.bold=True; run.font.color.rgb=title_color
    p.space_after = Pt(7)
    p = tf.add_paragraph(); p.text = body; p.space_after = Pt(0)
    for run in p.runs: run.font.name="Aptos"; run.font.size=Pt(body_size); run.font.color.rgb=INK_RGB
    return shape


def slide_base(prs, title, section=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid(); slide.background.fill.fore_color.rgb = PAPER_RGB
    add_text(slide, .55, .26, 12.1, .55, title, 25, INK_RGB, True, "Aptos Display")
    if section: add_text(slide, .58, .88, 12, .25, section.upper(), 9, GREEN_RGB, True, "Aptos")
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(.55), Inches(7.12), Inches(12.2), Inches(.012))
    line.fill.solid(); line.fill.fore_color.rgb=rgb("#D9DDD2"); line.line.fill.background()
    add_text(slide, .58, 7.18, 11.3, .2, "DawaLink · local-only core · technical implementation", 8, MUTED_RGB)
    add_text(slide, 12, 7.16, .6, .24, f"{len(prs.slides):02d}", 8, MUTED_RGB, align=PP_ALIGN.RIGHT)
    return slide


def ppt_logo(slide, name, x, y, w=.42, h=.42):
    """Embed a genuine, locally stored project/brand mark when available."""
    path = ROOT / "deliverables/assets/logos" / name
    if path.suffix == ".svg":
        png = path.with_suffix(".png")
        if not png.exists():
            cairosvg.svg2png(url=str(path), write_to=str(png), output_width=360, output_height=240)
        path = png
    with PILImage.open(path) as im:
        ratio=im.width/im.height
    if ratio >= w/h:
        slide.shapes.add_picture(str(path), Inches(x), Inches(y+(h-w/ratio)/2), width=Inches(w), height=Inches(w/ratio))
    else:
        slide.shapes.add_picture(str(path), Inches(x+(w-h*ratio)/2), Inches(y), width=Inches(h*ratio), height=Inches(h))


def arrow(slide, x1, y1, x2, y2, color=GREEN_RGB, width=2.2):
    line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    line.line.color.rgb = color; line.line.width = Pt(width); line.line.end_arrowhead = True
    return line


def label(slide, x, y, w, text, fill=INK_RGB, color=rgb("#FFFFFF")):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(.31))
    shape.fill.solid(); shape.fill.fore_color.rgb = fill; shape.line.fill.background()
    tf = shape.text_frame; tf.clear(); tf.margin_left=Inches(.05); tf.margin_right=Inches(.05); tf.margin_top=Inches(.015); tf.margin_bottom=0
    p=tf.paragraphs[0]; p.text=text; p.alignment=PP_ALIGN.CENTER
    for run in p.runs: run.font.name="Aptos"; run.font.size=Pt(9); run.font.bold=True; run.font.color.rgb=color
    return shape


def make_pptx(path):
    prs = Presentation(); prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
    # 1. Title
    s = slide_base(prs, "DawaLink", "Technical project · October 2026")
    add_text(s, .7, 1.5, 6.3, 1.15, "Multilingual Moroccan\nmedicine search and enquiry", 32, INK_RGB, True, "Aptos Display")
    add_text(s, .75, 4.2, 5.4, 1.2, "Local catalogue · Qwen request understanding · optional local OCR · copyable pharmacy message", 18, GREEN_RGB)
    add_box(s, 7.3, 1.55, 5.1, 4.2, "Measured project footprint", "9,908 catalogue records\n4,070 distinct brand strings\nQwen3 1.7B via local Ollama\n3 live conversation smoke prompts\nNo paid API or account required", fill=ACCENT_RGB, title_color=INK_RGB, body_size=17)

    # 2. User journey and live UI
    s = slide_base(prs, "One workflow, two ways to identify a product", "Product flow")
    add_text(s, .65, 1.15, 5.2, 5.55, "1  Describe the request in Darija, Arabic or French.\n\n2  Optionally upload a medicine-box photo for local OCR.\n\n3  Compare ranked candidates, strength and form.\n\n4  Select a real catalogue record.\n\n5  Correct package fields and copy a pharmacy question.\n\nStock is never claimed and no message is sent.", 16, INK_RGB)
    s.shapes.add_picture(str(screen_workflow), Inches(6), Inches(1.2), width=Inches(6.8))

    # 3. Architecture
    s = slide_base(prs, "Local LLM, grounded catalogue", "Implementation")
    add_box(s, .65, 2.0, 2.65, 2.0, "Browser", "HTML / CSS / JS\nrequest, image, selection", fill=rgb("#FFFFFF"))
    add_box(s, 3.75, 2.0, 2.65, 2.0, "WSGI API", "stdlib HTTP\nJSON and upload validation", fill=rgb("#FFFFFF"))
    add_box(s, 6.85, 2.0, 2.65, 2.0, "Qwen + core", "local JSON intent parse\ncatalogue · OCR · message", fill=PALE_RGB)
    add_box(s, 9.95, 2.0, 2.75, 2.0, "SQLite", "catalogue tables\nFTS5 and indexes", fill=rgb("#FFFFFF"))
    for x1,x2 in [(3.3,3.75),(6.4,6.85),(9.5,9.95)]:
        c=s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(3), Inches(x2), Inches(3)); c.line.color.rgb=GREEN_RGB; c.line.width=Pt(2); c.line.end_arrowhead=True
    add_box(s, 3.8, 4.8, 2.6, 1.25, "Tesseract 5.5", "Optional local engine\neng · fra · ara", fill=ACCENT_RGB, title_color=INK_RGB, body_size=12)
    c=s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(5.05), Inches(4.0), Inches(5.05), Inches(4.8)); c.line.color.rgb=GREEN_RGB; c.line.end_arrowhead=True
    add_text(s, 7.0, 4.8, 5.2, 1.2, "Prompts go to Ollama on loopback. There is no hosted LLM or cloud fallback; the model weights are downloaded once.", 16, INK_RGB)

    # 4. Data quality
    s = slide_base(prs, "The imported catalogue is real but incomplete", "Data engineering")
    add_text(s, .7, 1.18, 3.2, 1.3, "9,908 rows\n10 original fields\n0 duplicate IDs\n4,070 brand strings", 18, INK_RGB, True)
    add_text(s, 4.3, 1.16, 8.4, .45, "Missing or explicitly unavailable source values", 17, GREEN_RGB, True)
    field_values = [("EPI", 9908), ("Status", 1810), ("PPV", 1098), ("PH", 1098)]
    maxv=9908
    for j,(label,value) in enumerate(field_values):
        y=2+j*.83
        add_text(s, 4.35, y, 1.25, .3, label, 13, INK_RGB, True)
        bar=s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(5.55), Inches(y+.04), Inches(5.4*value/maxv), Inches(.24)); bar.fill.solid(); bar.fill.fore_color.rgb=GREEN_RGB; bar.line.fill.background()
        add_text(s, 11.15, y-.04, 1.3, .32, f"{value:,} · {value/maxv:.1%}", 12, MUTED_RGB)
    add_text(s, .75, 5.6, 11.8, .8, "The CSV export date was not retained. AMMPS showed 9,936 records / update 2026-10-01 at research time. Missing values stay blank; no price, status, manufacturer or availability is invented.", 14, INK_RGB)

    # 5. Request parsing
    s = slide_base(prs, "The local model understands the request", "Multilingual request handling")
    add_box(s, .7, 1.55, 4.0, 3.45, "Input", "3afak wach kayn\nDoliprane 1000 mg?", fill=rgb("#FFFFFF"), body_size=24)
    add_box(s, 5.1, 1.55, 3.15, 3.45, "Parsed from live model", "language: darija_latn\nintent: availability\nmedicine: Doliprane 1g\nstrength: 1g\ncity: Rabat", fill=PALE_RGB, body_size=15)
    add_box(s, 8.65, 1.55, 3.95, 3.45, "Catalogue confirmation", "3 exact-strength records\nBOITE DE 8 · effervescent\nBOITE DE 10 · COMPRIME SECABLE\nBOITE DE 10 · suppository\n\nCustomer chooses the exact pack.", fill=ACCENT_RGB, title_color=INK_RGB, body_size=15)
    add_text(s, .75, 5.55, 11.8, .75, "The live Qwen parse is grounded against the user’s words. Product names, strengths, package sizes and prices come from SQLite; symptom questions are redirected to a pharmacist.", 14, MUTED_RGB)

    # 6. Search
    s = slide_base(prs, "Rank by text and dosage evidence", "Catalogue retrieval")
    rows = [["Query", "Top result", "Evidence"], ["doliprene", "DOLIPRANE · 1 G", "fuzzy spelling"], ["AMOXICILLINE", "ALFAMOX · 1 G", "active substance"], ["DOLIPRANE 500 MG", "DOLIPRANE · 500 MG", "strength agreement"], ["DIACURE", "no result", "weak lookalike suppressed"]]
    t=s.shapes.add_table(len(rows),3, Inches(.75), Inches(1.45), Inches(11.9), Inches(3.65)).table
    for col,w in enumerate([3.3,4.0,4.6]):t.columns[col].width=Inches(w)
    for r,row in enumerate(rows):
        for c,value in enumerate(row):
            cell=t.cell(r,c);cell.text=value;cell.fill.solid();cell.fill.fore_color.rgb=INK_RGB if r==0 else (PALE_RGB if r%2 else rgb("#FFFFFF"))
            for p in cell.text_frame.paragraphs:
                for run in p.runs:run.font.name="Aptos";run.font.size=Pt(15 if r==0 else 14);run.font.bold=(r==0);run.font.color.rgb=rgb("#FFFFFF") if r==0 else INK_RGB
    add_text(s, .78, 5.55, 11.8, .7, "Search matching scores are not probabilities. Strength mismatch is penalized; similar products still require user selection.", 14, MUTED_RGB)

    # 7. OCR evidence
    s = slide_base(prs, "OCR runs locally; photo quality still limits it", "Image identification")
    add_text(s, .75, 1.35, 5.7, 4.9, "Pipeline\n1. Validate signature and dimensions\n2. Grayscale / contrast / upscale\n3. Tesseract (eng + fra + ara available)\n4. Normalize extracted text\n5. Strength-aware catalogue search\n6. Suppress generic or weak matches\n\nGenerated text-image smoke: DOLIPRANE 1 G read and matched.", 14, INK_RGB)
    add_box(s, 6.8, 1.35, 5.45, 4.5, "Real photo check · 1 image", "MIT test image; product DiaCURE manually transcribed.\n\nOCR: ENFANTS / CHILDREN; brand missed.\nVisible-text CER: 31.8%.\nMoroccan catalogue top-1/top-3: 0 / 1.\nExact product absent from Moroccan data.\n\nSafe result: no candidate, confirmation required.", fill=PALE_RGB, body_size=14)

    # 8 API
    s = slide_base(prs, "API and storage", "Contracts")
    add_text(s, .75, 1.35, 5.65, 5.15, "GET  /api/health\nGET  /api/medications?q=…\nGET  /api/medications/{id}\nPOST /api/assistant/message\nGET  /api/assistant/status\nPOST /api/recognize (multipart)\nPOST /api/pharmacy-request\nGET  /api/export\n\nSQLite `medications` preserves source fields plus normalized search keys, source and imported_at. FTS5 indexes product text.", 14, INK_RGB)
    add_box(s, 6.8, 1.55, 5.45, 3.1, "Pharmacy-request guard", "Message generation requires a valid catalogue ID. Strength, form and presentation can be edited by the user. Requested quantity and package size remain separate.", fill=ACCENT_RGB, title_color=INK_RGB, body_size=15)
    add_text(s, 6.95, 5.05, 5.1, .9, "No real-time pharmacy stock, contact directory, WhatsApp send, or location search is connected.", 15, MUTED_RGB)

    # 9 live enquiry screenshot
    s = slide_base(prs, "The user reviews and sends the enquiry", "Live application")
    s.shapes.add_picture(str(screen_message), Inches(2.9), Inches(1.2), width=Inches(7.5))
    add_text(s, .8, 6.25, 11.7, .45, "Captured from the running app after selecting catalogue ID 563 (DOLIPRANE 1 G).", 12, MUTED_RGB, align=PP_ALIGN.CENTER)

    # 10 tests
    s = slide_base(prs, "Verification and evaluation", "Observed results")
    add_box(s, .75, 1.5, 3.55, 2.2, "Core: 18 tests passed", "Earlier core suite\nManual current LLM smoke flow\nDarija · Arabic · French", fill=PALE_RGB)
    add_box(s, 4.85, 1.5, 3.55, 2.2, "3 LLM smoke prompts", "Live HTTP route\nIntent + catalogue + safety\nNot an accuracy benchmark", fill=ACCENT_RGB, title_color=INK_RGB)
    add_box(s, 8.95, 1.5, 3.55, 2.2, "1 real image", "Foreign-market failure\nNo Morocco positive sample", fill=rgb("#FFFFFF"))
    add_text(s, .85, 4.3, 11.6, 1.8, "Other probes: 6/6 catalogue top-three hits; 7 distinct strengths among the top 20 DOLIPRANE matches; all top 3 for DOLIPRANE 500 MG agree with the requested strength. Full details are in the JSON and Markdown evaluation artifacts.", 15, INK_RGB)

    # 11 reproduce and limits
    s = slide_base(prs, "Run locally and reproduce", "Reproducibility")
    add_box(s, .75, 1.4, 5.45, 3.2, "Required runtime", "ollama pull qwen3:1.7b\npython3 scripts/ingest_data.py\npython3 app.py\n\nOpen http://127.0.0.1:8000\n\nStart `ollama serve` if needed.", fill=PALE_RGB, body_size=15)
    add_box(s, 6.75, 1.4, 5.6, 3.2, "Tests and evaluation", "Ollama local API on 127.0.0.1:11434\nModel: qwen3:1.7b (~1.4 GB)\n\nOptional OCR: Tesseract 5 + eng/fra/ara data\nOptional build: scripts/build_deliverables.py", fill=rgb("#FFFFFF"), body_size=14)
    add_text(s, .8, 5.15, 11.8, 1.1, "The current flow supports enquiry preparation, not pharmacy discovery or live stock. Catalogue prices can be stale. Qwen can misunderstand dialect, so confirm the selected package. Voice input and inventory integration are not connected.", 14, MUTED_RGB)

    prs.core_properties.title="DawaLink Technical Presentation";prs.core_properties.author="DawaLink project"
    prs.save(path)


def main():
    out = ROOT / "deliverables"; out.mkdir(exist_ok=True)
    make_pdf(out / "DawaLink_Technical_Report.pdf")
    from scripts.build_presentation import make_pptx as make_presentation
    make_presentation(out / "DawaLink_Technical_Presentation.pptx")
    print(f"Built {out / 'DawaLink_Technical_Report.pdf'}")
    print(f"Built {out / 'DawaLink_Technical_Presentation.pptx'}")


if __name__ == "__main__":
    main()
