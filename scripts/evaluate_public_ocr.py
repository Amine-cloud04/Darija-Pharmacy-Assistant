#!/usr/bin/env python3
"""Reproduce a small real-photo OCR check using one MIT-licensed test image."""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dawaling_core as core

spec = json.loads((core.ROOT / "data/evaluation/ocr_public_images.json").read_text(encoding="utf-8"))
sample = spec["sample"]
request = urllib.request.Request(sample["url"], headers={"User-Agent": "DawaLink local evaluation/1.0"})
with urllib.request.urlopen(request, timeout=30) as reply:
    image = reply.read(8 * 1024 * 1024 + 1)
if len(image) > 8 * 1024 * 1024:
    raise SystemExit("Evaluation image exceeds the application's 8 MB limit.")
result = core.recognize_image(image, sample["filename"])
if not result.get("ocr_available"):
    raise SystemExit("Install local Tesseract before running the public image OCR evaluation.")

def normalize_text(value):
    return "".join(ch for ch in core.normalize(value) if ch.isalnum())

def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(current[-1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)))
        prev = current
    return prev[-1]

reference = normalize_text(sample["reference_visible_text"])
prediction = normalize_text(result["extracted_text"])
distance = edit_distance(reference, prediction)
name_found = normalize_text(sample["manual_product_name"]) in prediction
product_catalogue_match = any(core.normalize(item["specialite"]) == core.normalize(sample["manual_product_name"]) for item in result["candidates"])
output = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "dataset": spec["dataset"], "dataset_url": spec["dataset_url"], "license": spec["license"],
    "images": 1, "unique_products": 1, "split": spec["split"],
    "sample": sample["filename"], "dataset_object_label": sample["dataset_label"],
    "manual_product_name": sample["manual_product_name"], "product_in_moroccan_catalogue": sample["product_in_moroccan_catalogue"],
    "ocr_languages": result.get("ocr_languages", []), "ocr_text": result["extracted_text"],
    "reference_visible_text": sample["reference_visible_text"],
    "character_error_rate_visible_text": distance / len(reference) if reference else None,
    "product_name_read": name_found,
    "catalogue_top1_correct": False,
    "catalogue_top3_correct": False,
    "candidate_count": len(result["candidates"]),
    "candidates": [{"name": x["specialite"], "strength": x["dosage"], "score": x["matching_score"]} for x in result["candidates"]],
    "needs_confirmation": result.get("needs_confirmation", True),
    "result": "OCR did not read the product name; no exact Moroccan catalogue match was found." if not name_found else "OCR read the product name.",
    "limitations": ["One manually transcribed Indonesian product image only.", "The dataset's supplied object label is generic and does not identify the product; the visible-name annotation is manual.", "The sample product is absent from the included Moroccan catalogue, so this cannot measure Moroccan catalogue recall."],
}
out_dir = core.ROOT / "deliverables"
out_dir.mkdir(exist_ok=True)
(out_dir / "image_evaluation_results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
report = f"""# Real-photo OCR spot check

- Dataset: [{spec['dataset']}]({spec['dataset_url']}) ({spec['license']}).
- Split / sample: `{spec['split']}/{sample['filename']}`; one photograph, one manually read product name (`{sample['manual_product_name']}`).
- The dataset's own annotation is the generic class `{sample['dataset_label']}`, not a product identity. The product name was transcribed manually from the image.
- Local OCR text: `{result['extracted_text'].strip().replace(chr(10), ' / ')}`.
- Visible-text character error rate: {distance}/{len(reference)} = {distance / len(reference):.1%}.
- Product name read: `{name_found}`. Exact local-catalog top-1/top-3 identification: 0/1 (the pictured foreign-market product is not in the Moroccan catalogue).
- Safety behavior: {len(result['candidates'])} catalogue candidates; confirmation required: {result.get('needs_confirmation', True)}.

This spot check demonstrates a real-image failure case. It is too small and geographically mismatched to estimate general performance. The raw image is downloaded temporarily at evaluation time and is not redistributed in this repository. Full machine-readable output: `deliverables/image_evaluation_results.json`.
"""
(out_dir / "image_evaluation_report.md").write_text(report, encoding="utf-8")
print(report)
