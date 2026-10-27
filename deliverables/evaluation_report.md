# DawaLink evaluation report

Generated: 2026-10-27T14:58:13.706429+00:00

## Catalogue

- Source and normalized rows: 9908.
- Distinct brand values: 4070.
- Duplicate source IDs: 0.
- Missing EPI: 9908; status: 1810; PPV: 1098; PH: 1098.
- Ambiguous-name check: `DOLIPRANE` returned 17 candidates with 7 distinct strengths in the top 20. The UI requires product selection.
- Strength conflict probe: top-three results for `DOLIPRANE 500 MG` all agree with the parsed 500 mg strength: True.

## Request interpretation

Intent accuracy: 100.0% (16 manually authored cases). Language label accuracy: 100.0%. Medication name extraction: 7/7 named cases (100.0%). Clarification decisions: 16/16 (100.0%).

| Expected intent | Correct | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| availability_inquiry | 6/6 | 100.0% | 100.0% | 100.0% |
| medication_identification | 2/2 | 100.0% | 100.0% | 100.0% |
| pharmacy_location_inquiry | 1/1 | 100.0% | 100.0% | 100.0% |
| price_inquiry | 3/3 | 100.0% | 100.0% | 100.0% |
| product_information | 2/2 | 100.0% | 100.0% | 100.0% |
| unsupported_medical_question | 2/2 | 100.0% | 100.0% | 100.0% |

These hand-authored examples are not a representative or independently validated sample. Scores describe only these cases.

## Catalogue search probes

| Query | Top result | Top-1 hit | Top-3 hit |
|---|---|---|---|
| Doliprane 1 G | DOLIPRANE (1 G) | yes | yes |
| doliprene | DOLIPRANE (1 G) | yes | yes |
| AMOXICILLINE | ALFAMOX (1 G) | yes | yes |
| PARACETAMOL | ALGO (500   MG) | yes | yes |
| Amlodipine | AM-10 (10   MG) | yes | yes |
| DOLIPRANE 500 MG | DOLIPRANE (500   MG) | yes | yes |

## OCR and speech

The OCR engine is local Tesseract. The real-photo spot check used 1 MIT-licensed test image with one manually transcribed visible product name. OCR/name matching results are documented in `deliverables/image_evaluation_report.md`. It is a foreign-market product absent from the Moroccan catalogue, so this is an informative failure case, not a Moroccan benchmark. A positive Moroccan identification score cannot be established without a real labelled photo of a catalogue medicine. No speech transcription feature is implemented.

Reproduce request/search metrics with `python scripts/evaluate.py` and the image check with `python scripts/evaluate_public_ocr.py` (requires internet for that optional download and local Tesseract).
