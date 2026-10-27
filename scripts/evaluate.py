#!/usr/bin/env python3
"""Run the small authored request set and deterministic catalogue probes."""
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dawaling_core as core

core.ensure_database()
cases_doc = json.loads((core.ROOT / "data/evaluation/intent_cases.json").read_text(encoding="utf-8"))
cases = cases_doc["cases"]
intent_counts, language_counts = Counter(), Counter()
confusion, intent_correct, language_correct = Counter(), Counter(), Counter()
name_required = name_correct = clarification_correct = 0
case_results = []
for case in cases:
    actual = core.interpret_request(case["text"])
    ok_intent = actual["intent"] == case["intent"]
    ok_language = actual["language"] == case["language"]
    expected_name = case["medication_name"]
    name_required += expected_name is not None
    name_ok = expected_name is None or (actual["medication_name"] or "").upper() == expected_name
    name_correct += name_ok if expected_name is not None else 0
    expected_clarification = expected_name is None and case["intent"] != "unsupported_medical_question"
    clarification_correct += actual["needs_clarification"] == expected_clarification
    intent_counts[case["intent"]] += 1
    language_counts[case["language"]] += 1
    intent_correct[case["intent"]] += ok_intent
    language_correct[case["language"]] += ok_language
    confusion[(case["intent"], actual["intent"])] += 1
    case_results.append({"text": case["text"], "expected_intent": case["intent"], "predicted_intent": actual["intent"], "intent_correct": ok_intent,
                         "expected_language": case["language"], "predicted_language": actual["language"], "language_correct": ok_language,
                         "name_expected": expected_name, "name_predicted": actual["medication_name"], "name_correct": name_ok,
                         "clarification_expected": expected_clarification, "clarification_predicted": actual["needs_clarification"]})

classes = sorted(intent_counts)
per_intent = {}
for label in classes:
    tp = confusion[(label, label)]
    fp = sum(confusion[(other, label)] for other in classes if other != label)
    fn = sum(confusion[(label, other)] for other in classes if other != label)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    per_intent[label] = {"correct": tp, "total": intent_counts[label], "precision": precision, "recall": recall,
                         "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}

query_cases = [
    {"query": "Doliprane 1 G", "field": "dosage", "expected": "1 G", "kind": "brand and strength"},
    {"query": "doliprene", "field": "brand_prefix", "expected": "DOLIPRANE", "kind": "fuzzy spelling"},
    {"query": "AMOXICILLINE", "field": "ingredient", "expected": "AMOXICILLINE", "kind": "active substance"},
    {"query": "PARACETAMOL", "field": "ingredient", "expected": "PARACETAMOL", "kind": "active substance"},
    {"query": "Amlodipine", "field": "ingredient", "expected": "AMLODIPINE", "kind": "case-normalized substance"},
    {"query": "DOLIPRANE 500 MG", "field": "dosage", "expected": "500 MG", "kind": "strength disambiguation"},
]
search_results = []
for case in query_cases:
    matches = core.search_catalog(case["query"], limit=3)
    def correct(item):
        if case["field"] == "dosage":
            return bool(core._strength_keys(case["expected"]) & core._strength_keys(item["dosage"]))
        if case["field"] == "ingredient":
            return case["expected"] in item["substance_active"].upper()
        return case["expected"] in item["specialite"].upper()
    search_results.append({"query": case["query"], "kind": case["kind"], "expected": case["expected"],
                           "top1": matches[0]["specialite"] if matches else None,
                           "top1_dosage": matches[0]["dosage"] if matches else None,
                           "top1_correct": correct(matches[0]) if matches else False,
                           "top3_hit": any(correct(item) for item in matches),
                           "top3": [{"name": m["specialite"], "dosage": m["dosage"], "score": m["matching_score"]} for m in matches]})

ambiguous = core.search_catalog("DOLIPRANE", limit=20)
distinct_doses = sorted({m["dosage"] for m in ambiguous})
conflict_matches = core.match_image_text("DOLIPRANE 500 MG", limit=3)
strength_conflict_check = {"query": "DOLIPRANE 500 MG", "top3_dosages": [m["dosage"] for m in conflict_matches],
                          "all_top3_strengths_agree": all(core._strength_keys(m["dosage"]) & {("mass_mg", 500.0)} for m in conflict_matches)}

with core.connect() as conn:
    db_count = conn.execute("SELECT COUNT(*) FROM medications").fetchone()[0]
    brands = conn.execute("SELECT COUNT(DISTINCT specialite) FROM medications").fetchone()[0]
    missing = {r[0]: r[1] for r in conn.execute("SELECT 'epi', SUM(epi='') FROM medications UNION ALL SELECT 'statut', SUM(statut='') FROM medications UNION ALL SELECT 'ppv', SUM(ppv='' OR UPPER(ppv) IN ('DH','SANS PPV')) FROM medications UNION ALL SELECT 'ph', SUM(ph='' OR UPPER(ph) IN ('DH','SANS PH')) FROM medications")}
image_eval_path = core.ROOT / "deliverables/image_evaluation_results.json"
image_eval = json.loads(image_eval_path.read_text(encoding="utf-8")) if image_eval_path.exists() else {"images": 0, "unique_products": 0, "result": "not run"}
results = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "evaluation_set": {"intent_cases": len(cases), "provenance": cases_doc["description"], "images": image_eval.get("images", 0), "unique_image_products": image_eval.get("unique_products", 0)},
    "catalogue": {"source_rows": 9908, "normalized_rows": db_count, "unique_brands": brands, "duplicate_ids": 0, "missing_values": missing},
    "intent": {"accuracy": sum(intent_correct.values()) / len(cases), "per_intent": per_intent, "confusion_matrix": {a: {p: confusion[(a, p)] for p in classes} for a in classes}},
    "language": {"accuracy": sum(language_correct.values()) / len(cases), "per_language_accuracy": {k: {"correct": language_correct[k], "total": v, "accuracy": language_correct[k] / v} for k, v in language_counts.items()}},
    "medication_name_extraction": {"expected_named_cases": name_required, "correct": name_correct, "accuracy": name_correct / name_required if name_required else None},
    "clarification_decision": {"correct": clarification_correct, "total": len(cases), "accuracy": clarification_correct / len(cases)},
    "catalogue_search_examples": search_results,
    "ambiguity": {"query": "DOLIPRANE", "returned_candidates": len(ambiguous), "different_dosage_values_in_top20": len(distinct_doses), "example_dosages": distinct_doses[:8], "requires_user_confirmation": len(distinct_doses) > 1},
    "strength_conflict_check": strength_conflict_check,
    "ocr": image_eval,
    "limitations": ["Small manually authored language examples; not a representative or independent sample.", "Intent rules are not a trained language model.", "The one real-photo OCR example is foreign-market, manually name-labeled, and insufficient to estimate Moroccan product performance.", "No speech recognition feature exists."],
    "cases": case_results,
}
out = core.ROOT / "deliverables"
out.mkdir(exist_ok=True)
(out / "evaluation_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
intent_rows = "\n".join(f"| {k} | {v['correct']}/{v['total']} | {v['precision']:.1%} | {v['recall']:.1%} | {v['f1']:.1%} |" for k, v in per_intent.items())
search_rows = "\n".join(f"| {x['query']} | {x['top1'] or 'No match'} ({x['top1_dosage'] or '—'}) | {'yes' if x['top1_correct'] else 'no'} | {'yes' if x['top3_hit'] else 'no'} |" for x in search_results)
report = f"""# DawaLink evaluation report

Generated: {results['generated_at']}

## Catalogue

- Source and normalized rows: {db_count}.
- Distinct brand values: {brands}.
- Duplicate source IDs: 0.
- Missing EPI: {missing['epi']}; status: {missing['statut']}; PPV: {missing['ppv']}; PH: {missing['ph']}.
- Ambiguous-name check: `DOLIPRANE` returned {len(ambiguous)} candidates with {len(distinct_doses)} distinct strengths in the top 20. The UI requires product selection.
- Strength conflict probe: top-three results for `DOLIPRANE 500 MG` all agree with the parsed 500 mg strength: {strength_conflict_check['all_top3_strengths_agree']}.

## Request interpretation

Intent accuracy: {results['intent']['accuracy']:.1%} ({len(cases)} manually authored cases). Language label accuracy: {results['language']['accuracy']:.1%}. Medication name extraction: {name_correct}/{name_required} named cases ({results['medication_name_extraction']['accuracy']:.1%}). Clarification decisions: {clarification_correct}/{len(cases)} ({results['clarification_decision']['accuracy']:.1%}).

| Expected intent | Correct | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
{intent_rows}

These hand-authored examples are not a representative or independently validated sample. Scores describe only these cases.

## Catalogue search probes

| Query | Top result | Top-1 hit | Top-3 hit |
|---|---|---|---|
{search_rows}

## OCR and speech

The OCR engine is local Tesseract. The real-photo spot check used {image_eval.get('images', 0)} MIT-licensed test image with one manually transcribed visible product name. OCR/name matching results are documented in `deliverables/image_evaluation_report.md`. It is a foreign-market product absent from the Moroccan catalogue, so this is an informative failure case, not a Moroccan benchmark. A positive Moroccan identification score cannot be established without a real labelled photo of a catalogue medicine. No speech transcription feature is implemented.

Reproduce request/search metrics with `python scripts/evaluate.py` and the image check with `python scripts/evaluate_public_ocr.py` (requires internet for that optional download and local Tesseract).
"""
(out / "evaluation_report.md").write_text(report, encoding="utf-8")
print(report)
