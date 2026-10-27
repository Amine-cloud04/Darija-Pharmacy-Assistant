# DawaLink implementation plan

## Initial audit findings

- The workspace was empty; the linked Git repository was cloned here.
- At the start of work, the app was a Python standard-library WSGI server, SQLite catalogue, and static HTML/CSS/JS client. Chat depended on a paid/credentialed OpenAI Responses API.
- `moroccan_medications.csv` has 9,908 records and ten columns (`id`, `specialite`, `substance_active`, `dosage`, `forme`, `presentation`, `epi`, `statut`, `ppv`, `ph`). IDs are unique; EPI is blank for every record. Status is blank for 1,810 rows; PPV/PH are unavailable in 1,098 rows each. There are 4,070 distinct brand strings. `ammps_cards.csv` is an empty, one-byte file.
- No project dependencies or usable test suite are present. `python -m unittest discover -v` fails while importing the scraper file because `pandas` is not installed. The file named `test_scrap.py` is a 826-page scraper, not tests; it must not be executed as a test.
- Python 3.14, SQLite FTS5, 4 CPU cores and 14 GiB RAM are available. Tesseract is not installed at baseline. There are no medicine photographs or labelled image evaluation examples in the repository.
- AMMPS's public search page was reachable and showed 9,936 results with an update date of 2026-10-01 at inspection. The local CSV contains 9,908; this does not prove exact parity or authorize bulk republication. No separately downloadable, documented CNOPS dataset was identified during the initial source check. The existing export remains the only imported data source until a licensable file is available.

## Implementation sequence

1. Replace the external chat dependency with local multilingual request parsing and catalogue-grounded search.
2. Add a reproducible CSV-to-SQLite ingestion and quality report while preserving source files and provenance.
3. Add explainable candidate ranking, image upload validation and optional local Tesseract OCR.
4. Add pharmacy enquiry generation and connect all actions to the existing interface.
5. Add standard-library automated tests and evaluation scripts, including explicit limits where labelled images are absent.
6. Update setup/source documentation and generate factual PDF and PowerPoint deliverables from measured outputs.

## Current implementation

- The product flow is a multi-turn chat, exact catalogue confirmation, and a copyable availability/price question. UI actions are connected to the WSGI API and local SQLite catalogue.
- `assistant_service.py` uses a locally installed Ollama Qwen3 1.7B model with schema-constrained output. It is configured for loopback only, grounds extracted details in the user's words, and searches the included catalogue for real candidate IDs. No hosted model fallback exists.
- The assistant has been manually exercised over HTTP in Darija, Arabic and French, including a symptom safety response. The LLM route has only smoke coverage; no general accuracy claim is made.
- Pharmacy discovery, real-time stock, live pricing, prescription interpretation, speech input, and sending messages remain unavailable. The UI states these limits and only generates a message after a catalogue product is selected.
- The OCR setup detects the project-local Tesseract extraction automatically. The evaluation artifacts document one real-photo brand-recognition failure and do not claim Moroccan photo performance.

## Acceptance criteria

- Text interpretation, local catalogue search/details, image OCR when Tesseract is installed, and copyable enquiry generation work without secrets or paid services.
- API and UI share the same local SQLite catalogue and business logic.
- Missing catalogue fields and uncertain image matches remain explicit.
- Tests cover catalogue ingestion/search, multilingual structured extraction, ambiguous matching, APIs, and enquiry output. No OCR accuracy is claimed without labelled real medicine photographs.
- Reports and presentation accurately state data provenance, tested features, actual metrics, and unmeasured areas.
