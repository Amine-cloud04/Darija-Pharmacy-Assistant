"""Build the visual DawaLink slide deck with sourced brand assets."""
from pathlib import Path
import sys
from PIL import Image as PILImage

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_deliverables import (Presentation, Inches, Pt, PP_ALIGN, MSO_SHAPE,
    MSO_CONNECTOR, RGBColor, rgb, slide_base, add_text, add_box, label, arrow,
    ppt_logo, INK_RGB, GREEN_RGB, ACCENT_RGB, PALE_RGB, MUTED_RGB, screen_workflow,
    screen_message)

WHITE=rgb('#FFFFFF')
SCREEN_CROP=ROOT/'deliverables/screenshots/DawaLink_presentation_crop.png'
if not SCREEN_CROP.exists():
    with PILImage.open(screen_workflow) as image:
        image.crop((110,365,1310,1180)).save(SCREEN_CROP)

def make_pptx(path):
    prs=Presentation(); prs.slide_width=Inches(13.333); prs.slide_height=Inches(7.5)
    s=slide_base(prs,'DawaLink','A real pharmacy question, made easier · October 2026')
    add_text(s,.72,1.45,6.65,.65,'“3afak wach kayn Doliprane 1g f Rabat?”',23,GREEN_RGB,True,'Aptos Display')
    add_text(s,.75,2.45,6.2,1.6,'A customer wants a clear answer about one exact medicine pack. DawaLink helps them identify it and prepare a useful pharmacy question—in Darija, Arabic or French.',20,INK_RGB)
    add_box(s,8.05,1.55,4.4,3.8,'The product promise','Understand the request\nConfirm the exact catalogue item\nPrepare an editable enquiry\n\nThe pharmacy supplies the real stock answer.',ACCENT_RGB,INK_RGB,17)
    add_text(s,.78,5.65,11.7,.5,'Local-first · 9,908 imported catalogue rows · free/open-source runtime · no hosted AI or paid API',14,MUTED_RGB)

    s=slide_base(prs,'User story · from uncertainty to a useful question','The experience')
    add_box(s,.8,1.35,11.75,1.12,'Customer need','As a person looking for a medicine, I want to explain what I need in my own language, so I can identify the right catalogue item and ask a pharmacy clearly without guessing availability.',PALE_RGB,body_size=13)
    add_box(s,.75,3.05,3.55,2.15,'1 · Explain the need','“3afak wach kayn Doliprane 1g f Rabat?”\n\nThe local model extracts intent, medicine, strength and city.',WHITE,body_size=13)
    add_box(s,4.85,3.05,3.55,2.15,'2 · Confirm the pack','DawaLink shows three real 1 G records. The customer compares form and package, then selects ID 563.',PALE_RGB,body_size=13)
    add_box(s,8.95,3.05,3.55,2.15,'3 · Prepare the question','Review the quantity, city and Darija wording. Copy it to contact a pharmacy.',ACCENT_RGB,INK_RGB,13)
    arrow(s,4.3,4.12,4.78,4.12); arrow(s,8.4,4.12,8.88,4.12)
    add_text(s,.9,5.85,11.5,.7,'Success means an exact, customer-confirmed product and a useful enquiry. The customer decides what to send; the pharmacy provides the actual stock answer.',15,INK_RGB,align=PP_ALIGN.CENTER)

    s=slide_base(prs,'The customer stays in control at every step','Observed live workflow')
    s.shapes.add_picture(str(SCREEN_CROP),Inches(2.5),Inches(1.15),width=Inches(8.3))
    add_text(s,.9,6.82,11.4,.2,'Captured from the running app · selected ID 563 · customer copies the message; inventory is not verified.',10,MUTED_RGB,align=PP_ALIGN.CENTER)

    s=slide_base(prs,'Technical architecture · local, grounded, inspectable','Runtime design')
    b=s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,Inches(.55),Inches(1.4),Inches(12.2),Inches(4.95))
    b.fill.solid(); b.fill.fore_color.rgb=rgb('#E8EFE6'); b.fill.transparency=16; b.line.color.rgb=GREEN_RGB; b.line.width=Pt(1.3)
    label(s,.82,1.22,2.4,'ONE DEVICE · LOCAL SERVICES',GREEN_RGB)
    add_box(s,.85,2.15,2.05,1.35,'Browser UI','HTML · CSS · JS\ntext / photo / confirm',WHITE,body_size=11)
    ppt_logo(s,'html5.png',1.53,1.73,.28,.28); ppt_logo(s,'javascript.png',1.88,1.73,.28,.28)
    add_box(s,3.55,2.15,2.15,1.35,'Python WSGI API','app.py · validation\nJSON + multipart',WHITE,body_size=11)
    ppt_logo(s,'python.svg',4.46,1.73,.28,.28)
    add_box(s,6.45,2.15,2.15,1.35,'DawaLink core','intent grounding\nsearch · request guard',WHITE,body_size=11)
    add_box(s,10.05,2.15,2.2,1.35,'SQLite · FTS5','9,908 records\nproduct facts only',WHITE,body_size=11)
    ppt_logo(s,'sqlite.png',10.77,1.73,.75,.32)
    arrow(s,2.9,2.8,3.5,2.8); arrow(s,5.7,2.8,6.4,2.8); arrow(s,8.6,2.8,10.,2.8); arrow(s,10.,3.12,8.6,3.12)
    label(s,2.92,2.38,.56,'HTTP'); label(s,5.79,2.38,.54,'JSON'); label(s,8.83,2.38,.95,'SQL search')
    add_box(s,6.1,4.35,2.1,1.25,'Ollama runtime','127.0.0.1:11434\nlocal chat API',WHITE,body_size=10)
    ppt_logo(s,'ollama.png',6.8,4.0,.4,.3)
    add_box(s,8.85,4.35,2.,1.25,'Qwen3 1.7B','schema-constrained\nrequest extraction',ACCENT_RGB,INK_RGB,10)
    ppt_logo(s,'qwen.jpg',9.24,4.02,.82,.24)
    arrow(s,7.5,3.53,7.15,4.3); arrow(s,8.25,4.98,8.8,4.98); label(s,7.25,3.78,1.25,'local prompt')
    add_box(s,3.25,4.35,2.15,1.25,'Tesseract OCR','optional image text\neng · fra · ara',WHITE,body_size=10)
    arrow(s,4.65,3.53,4.65,4.3); arrow(s,5.4,4.5,6.4,3.5); label(s,4.15,3.78,.95,'photo upload')
    label(s,5.65,3.92,1.1,'OCR text',GREEN_RGB)
    add_text(s,.88,5.88,11.35,.32,'Browser → validated API → local interpretation and retrieval → candidate records → user confirms → editable message to copy',11,GREEN_RGB,True,align=PP_ALIGN.CENTER)
    add_text(s,.85,6.48,11.7,.42,'No cloud LLM · no external pharmacy directory · no live inventory · no automatic sending',12,MUTED_RGB,align=PP_ALIGN.CENTER)

    s=slide_base(prs,'The model interprets intent; the catalogue supplies facts','Trust boundary')
    add_box(s,.8,1.5,3.55,3.4,'User’s words','“3afak wach kayn\nDoliprane 1g\nf Rabat?”',WHITE,body_size=20)
    add_box(s,4.9,1.5,3.55,3.4,'Qwen3 structured parse','intent: availability\nmedicine: Doliprane\nstrength: 1 G\ncity: Rabat',PALE_RGB,body_size=15)
    add_box(s,9.,1.5,3.55,3.4,'SQLite candidates','3 catalogue records\nall 1 G\nID 563 selected\nBOITE DE 8',ACCENT_RGB,INK_RGB,15)
    arrow(s,4.35,3.2,4.85,3.2); arrow(s,8.45,3.2,8.95,3.2)
    add_text(s,.9,5.45,11.5,.65,'The model is a language interface—not a medicine database. Search results are grounded, strength conflicts are filtered, and the customer confirms the exact pack.',14,INK_RGB,align=PP_ALIGN.CENTER)

    s=slide_base(prs,'Real catalogue data, with its gaps kept visible','Data pipeline')
    add_text(s,.8,1.35,3.35,2.35,'9,908 source rows\n10 original columns\n0 duplicate IDs\n4,070 brand strings',20,INK_RGB,True)
    add_text(s,4.55,1.35,7.9,.42,'Missing or unavailable values in supplied export',16,GREEN_RGB,True)
    for j,(name,val) in enumerate([('EPI',9908),('Status',1810),('PPV',1098),('PH',1098)]):
        y=2.05+j*.7; add_text(s,4.6,y,1.25,.28,name,12,INK_RGB,True)
        bar=s.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(5.75),Inches(y+.03),Inches(5.05*val/9908),Inches(.2));bar.fill.solid();bar.fill.fore_color.rgb=GREEN_RGB;bar.line.fill.background()
        add_text(s,10.95,y-.03,1.35,.3,f'{val:,} · {val/9908:.0%}',11,MUTED_RGB)
    add_box(s,4.1,4.62,2.0,.82,'Source CSV','9,908 rows',WHITE,body_size=10)
    add_box(s,6.45,4.62,2.65,.82,'ingest_data.py','normalize + validate',PALE_RGB,body_size=10)
    add_box(s,9.45,4.62,2.55,.82,'SQLite · FTS5','atomic rebuild',WHITE,body_size=10)
    arrow(s,6.12,5.03,6.4,5.03); arrow(s,9.12,5.03,9.4,5.03)
    add_box(s,.85,5.55,11.6,.95,'Provenance matters','Repository export date is unknown. Values are preserved as supplied; historical price fields are not live pharmacy prices. No missing manufacturer, stock or status facts are filled in.',WHITE,body_size=12)

    s=slide_base(prs,'Search narrows the choice; the customer makes it','Catalogue retrieval')
    rows=[['Query','Observed result','What the system uses'],['doliprene','DOLIPRANE · 1 G','normalized + fuzzy text'],['AMOXICILLINE','ALFAMOX · 1 G','active ingredient'],['DOLIPRANE 500 MG','DOLIPRANE · 500 MG','strength agreement'],['DIACURE','no result','weak lookalike suppressed']]
    t=s.shapes.add_table(len(rows),3,Inches(.85),Inches(1.55),Inches(11.6),Inches(3.5)).table
    for col,w in enumerate([3.1,3.8,4.7]): t.columns[col].width=Inches(w)
    for r,row in enumerate(rows):
        for c,value in enumerate(row):
            cell=t.cell(r,c);cell.text=value;cell.fill.solid();cell.fill.fore_color.rgb=INK_RGB if r==0 else (PALE_RGB if r%2 else WHITE)
            for p in cell.text_frame.paragraphs:
                for run in p.runs:run.font.name='Aptos';run.font.size=Pt(14 if r==0 else 13);run.font.bold=(r==0);run.font.color.rgb=WHITE if r==0 else INK_RGB
    add_text(s,.9,5.48,11.5,.75,'Search scores are matching signals, not calibrated probabilities. Similar products remain separate choices; strength and form must be checked.',14,MUTED_RGB)

    s=slide_base(prs,'Photo identification is an optional local path','Image processing')
    add_text(s,.85,1.45,5.4,4.8,'1 · Validate file type and size\n\n2 · Preprocess locally\n\n3 · Tesseract reads visible text\n\n4 · Search the same SQLite catalogue\n\n5 · Customer reviews any candidate',16,INK_RGB)
    add_box(s,6.65,1.45,5.55,4.55,'Evidence: one real photo spot check','MIT test image showed a foreign-market DiaCURE pack. OCR read ENFANTS / CHILDREN and missed the brand; catalogue result was safely empty.\n\nThis is a documented failure case—not a performance claim. A Moroccan product photo benchmark is still needed.',PALE_RGB,body_size=15)

    s=slide_base(prs,'Small API, clear responsibilities','Implementation')
    add_box(s,.85,1.4,5.45,4.7,'Browser ↔ Python WSGI','GET  /api/health\nGET  /api/medications?q=…\nGET  /api/medications/{id}\nPOST /api/assistant/message\nGET  /api/assistant/status\nPOST /api/recognize\nPOST /api/pharmacy-request\nGET  /api/export',WHITE,body_size=13)
    add_box(s,6.95,1.4,5.4,2.2,'SQLite storage','Original source columns + normalized search keys, source, import timestamp; indexed FTS5 product text.',PALE_RGB,body_size=14)
    add_box(s,6.95,4.05,5.4,2.05,'Enquiry guard','Generation requires a valid catalogue ID. User reviews the product, quantity, city and wording, then copies the message.',ACCENT_RGB,INK_RGB,14)

    s=slide_base(prs,'A clear enquiry the customer can review and copy','Product outcome')
    s.shapes.add_picture(str(SCREEN_CROP),Inches(2.5),Inches(1.13),width=Inches(8.3))
    add_text(s,.85,6.82,11.6,.2,'Product ID 563 · DOLIPRANE 1 G · BOITE DE 8 · 1 boîte · Rabat · captured in the running app',10,MUTED_RGB,align=PP_ALIGN.CENTER)

    s=slide_base(prs,'What has been verified—and what has not','Evaluation')
    add_box(s,.8,1.45,3.55,2.1,'Core logic','18 earlier tests passed\n6/6 catalogue probes hit top 3',PALE_RGB,body_size=14)
    add_box(s,4.9,1.45,3.55,2.1,'LLM flow','3 live smoke prompts\nDarija · Arabic · French\nNo accuracy benchmark',ACCENT_RGB,INK_RGB,13)
    add_box(s,9.,1.45,3.55,2.1,'Photo evidence','1 foreign photo\nbrand missed\nNo Morocco benchmark',WHITE,body_size=13)
    add_text(s,.9,4.15,11.5,1.3,'Scope today: conversational intent extraction, catalogue search, optional text OCR and message preparation. Not present: diagnosis, dosing advice, live prices, stock, pharmacy directory, voice, ordering or automatic messaging.',16,INK_RGB,align=PP_ALIGN.CENTER)

    s=slide_base(prs,'Run the same local stack','Reproducibility')
    add_box(s,.85,1.45,5.45,3.35,'1 · Load the model','ollama pull qwen3:1.7b\n\nStart Ollama if needed: ollama serve',PALE_RGB,body_size=15)
    add_box(s,6.95,1.45,5.45,3.35,'2 · Prepare and launch','python3 scripts/ingest_data.py\npython3 app.py\n\nOpen http://127.0.0.1:8000',WHITE,body_size=15)
    add_text(s,.9,5.35,11.5,.8,'Ollama serves Qwen3 1.7B on loopback. Tesseract 5 and language packs are optional for image OCR. Model weights are downloaded separately; no paid service is required.',14,MUTED_RGB,align=PP_ALIGN.CENTER)
    prs.core_properties.title='DawaLink — Local Moroccan Medication Enquiry'; prs.core_properties.author='DawaLink project'
    prs.core_properties.subject='User story, local system architecture, tool provenance and evidence'
    prs.save(path)
