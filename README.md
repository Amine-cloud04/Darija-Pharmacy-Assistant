# DawaLink

[![CI](https://github.com/Amine-cloud04/Darija-Pharmacy-Assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/Amine-cloud04/Darija-Pharmacy-Assistant/actions/workflows/ci.yml)

DawaLink is a local-first Moroccan medicine catalogue and pharmacy enquiry assistant. A user can describe a stock or price question in Moroccan Darija, Arabic or French; the local Qwen model extracts the request and medicine details, the app checks them against the included catalogue, the user confirms the exact product, and the app prepares a message they can copy to their pharmacy. A medicine-box photo can also be read with local Tesseract OCR.

It does not diagnose, prescribe, assess interactions, verify stock, contact pharmacies, or send messages. Catalogue registration, price and status are not evidence of current availability. Ask a pharmacist or clinician about medical decisions.

## What runs locally

The intended customer journey and pharmacy information needs are described in [USER_STORY.md](USER_STORY.md).

- Python standard-library WSGI server and SQLite, including FTS5 catalogue indexing.
- Brand, active substance, strength, form and presentation search with normalized Arabic/French spelling and fuzzy ranking.
- Multi-turn conversational understanding through Qwen3 1.7B running locally with Ollama. The model extracts intent and user-stated details into a constrained JSON schema. It does not invent catalogue records: candidate product IDs and displayed prices come from SQLite. A small local safety guard routes clear personal treatment questions to a pharmacist.
- Optional JPEG, PNG and WebP OCR through the local Tesseract executable. English, French and Arabic language data are used when installed. OCR scores are matching scores, not probabilities.
- Candidate confirmation and editable French, Darija Latin or Darija Arabic pharmacy enquiry text.
- No hosted API, API key or per-request fee. User questions are sent only to the local Ollama service on loopback; no cloud fallback is configured. The model weights require a one-time download (~1.4 GB). Catalogue browsing and image OCR can still be used if Ollama is stopped.

No speech recognition is implemented. Browser voice recognition can depend on remote browser services and is outside this local workflow.

## Data and provenance

`moroccan_medications.csv` is preserved as supplied by the linked repository. It has 9,908 rows, 10 columns and unique IDs. The AMMPS source export date was not retained. The official AMMPS public search page was reachable during project work and then showed 9,936 entries and an update date of 2026-10-01; the repository export therefore should not be treated as a current complete source. Current source: <https://ammps.gov.ma/recherche-medicaments>.

The catalogue has 4,070 distinct brand strings. In the imported file, EPI is blank for all 9,908 rows, status for 1,810, and PPV/PH each have 1,098 unavailable values (blank or explicit `DH`/`SANS PPV`/`SANS PH`). Values are not filled from assumptions. `ammps_cards.csv` is empty. The app preserves records and source fields; it does not merge near-duplicate products.

The Moroccan Open Data portal lists a CNOPS “Référentiel des médicaments” as XLSX under ODbL, but it points to a 2014 file. The portal was returning an error during this implementation, and its old resource host could not be resolved from this environment. That reference is not mixed into the catalogue because its data could not be retrieved and its prices/status are old. The portal describes attribution and share-alike obligations: <https://www.data.gov.ma/fr/node/14>; dataset listing: <https://www.data.gov.ma/data/fr/dataset/?groups=sante&license_id=odc-odbl&organization=caisse-nationale-des-organismes-de-prevoyance-sociale&res_format=XLSX&tags=Cnops&tags=m%C3%A9dicament&tags=princeps>.

The AMMPS website is a public official register. No separate bulk-download license or reuse terms were identified for the supplied export. This project does not claim the export is licensed for redistribution; review AMMPS terms before republishing the catalogue. No extra data is copied into the repository. Darija Open Dataset was investigated but not used: its translation material is not pharmacy intent data and is not needed for this rules-based baseline.

## Requirements and launch

- Python 3.11 or newer (tested here with Python 3.14).
- Ollama with the `qwen3:1.7b` model for conversational text understanding.
- Tesseract OCR 5 with `eng`, `fra`, and `ara` language packs for image recognition.

Install the free Ollama runtime from its [official Linux instructions](https://docs.ollama.com/linux). Then, from the repository root, use two terminals:

```bash
# Terminal 1. If Ollama is not already running as a service:
ollama serve
```

```bash
# Terminal 2. Download the open-weight Qwen3 1.7B model once (~1.4 GB), then start DawaLink.
ollama pull qwen3:1.7b
python3 scripts/ingest_data.py
python3 app.py
```

Open <http://127.0.0.1:8000>. The assistant sends prompts only to Ollama at `127.0.0.1:11434`; if it is unavailable, the app shows setup instructions and does not send text to a cloud model. Catalogue browsing remains available. The Qwen3 family’s 1.7B model is released under Apache 2.0; see the [Qwen team’s model announcement](https://qwenlm.github.io/blog/qwen3/). SQLite `pharmacy.db` is generated locally and ignored by Git. A changed source CSV triggers a rebuild. To force a rebuild and refresh its quality report, run `python3 scripts/ingest_data.py --force`.

On Debian/Ubuntu, optional French/Arabic OCR can be installed with:

```bash
sudo apt install tesseract-ocr tesseract-ocr-fra tesseract-ocr-ara
```

The app runs without Tesseract and reports that OCR is unavailable. No model weights are downloaded automatically. Uploads are limited to 8 MB, checked by image signature, written to a temporary file and deleted after OCR.

## Tests and evaluation

GitHub Actions runs the unit suite and local evaluation on pushes and pull requests to `main`, then builds the PDF report and presentation. The built files are attached to each successful workflow run as downloadable artifacts. This repository has no hosted deployment target; the application remains a local-first service.

```bash
python3 -m unittest discover -s tests -v
python3 scripts/evaluate.py
```

`data/evaluation/intent_cases.json` contains 16 manually authored examples, not a representative or independently validated dataset. `deliverables/evaluation_results.json` and `deliverables/evaluation_report.md` are generated from actual code. The observed intent and language scores apply only to that small set. One real MIT test photo was checked: OCR missed its manually read foreign-market product name (visible-text CER 31.8%); the product is absent from the Moroccan catalogue, so this is not a Moroccan identification benchmark. The image is downloaded temporarily and is not included. A positive Moroccan photo test still needs a labelled image of a catalogue product. `test_scrap.py` is a network scraper, not a test suite; do not run it as a test.

## API

The same functions power the web interface and API. All endpoints bind to localhost only.

- `GET /api/health`
- `GET /api/medications?q=Doliprane&page=1&per_page=20`
- `GET /api/medications/{id}`
- `GET /api/assistant/status`
- `POST /api/assistant/message` JSON: `{"messages":[{"role":"user","content":"3afak wach kayn Doliprane 1g f Rabat?"}]}`. Uses local Ollama and returns grounded catalogue candidates.
- `POST /api/interpret` deterministic compatibility endpoint: `{"text":"3afak wach kayn Doliprane 1000 mg?"}`
- `POST /api/recognize` multipart form field `image` (JPEG, PNG or WebP)
- `POST /api/pharmacy-request` JSON, e.g. `{"catalog_id":"563","requested_quantity":"1 boîte","location":"Rabat","language":"fr","question_type":"both"}`
- `GET /api/export?q=Doliprane`

Interactive OpenAPI documentation is not provided; the API uses the existing dependency-free WSGI server. Invalid input receives JSON errors. The complete web UI is at `/`.

## Architecture

`app.py` handles HTTP and validation. `assistant_service.py` connects the conversational UI to Ollama over loopback, constrains model output to a JSON schema, grounds extracted details in the conversation, and retrieves products from the catalogue. `dawaling_core.py` implements CSV import, SQLite/FTS5, search, OCR invocation, strength/form matching and enquiry generation. `static/` contains the chat and confirmation workflow. `scripts/ingest_data.py` produces `data/processed/data_quality_report.json`; `scripts/evaluate.py` regenerates the rule-based baseline evaluation artifacts.

## Known limits

- No labelled Moroccan catalogue photos are included. One foreign-market image was evaluated as a failure spot check, but it cannot estimate OCR or catalogue-match performance for Moroccan products. OCR operation itself needs local Tesseract and language packs.
- The 1.7B model is compact and can misunderstand dialect or entity details. The UI asks the user to confirm an exact catalogue item; details such as strength and quantity are checked against what was written. The model is not a medical adviser.
- The generated message is reviewed and sent by the user. Pharmacy stock, local directories, delivery and live prices are not connected. Catalogue PPV values may be stale.
- The legacy AMMPS export has no retained source date and missing fields. The source web page has since reported a newer total.
- No pharmacy inventory, pharmacy directory, messaging integration, speech recognition, or clinical decision support exists.
- Uploaded image processing and assistant prompts stay on the device by default. No remote AI endpoint or fallback is configured.

## Deliverables

Build the technical PDF and slide deck with the pinned build-time packages (the Python app itself has no third-party package dependency; conversational use additionally requires the Ollama runtime and model):

```bash
python3 -m pip install -r requirements-deliverables.txt
python3 scripts/build_deliverables.py
```

The optional OCR dependencies are listed in `requirements-ocr.txt`.

- `deliverables/DawaLink_Technical_Report.pdf`
- `deliverables/DawaLink_Technical_Presentation.pptx`
- `deliverables/evaluation_results.json`
- `deliverables/evaluation_report.md`
- `deliverables/image_evaluation_results.json` and `deliverables/image_evaluation_report.md`
- `deliverables/screenshots/` (captured from the running application)
