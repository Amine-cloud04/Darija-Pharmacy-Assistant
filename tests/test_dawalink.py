import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import dawaling_core as core
import app


class CatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        core.ensure_database()

    def test_catalogue_record_and_search(self):
        results = core.search_catalog("Doliprane 1 g", limit=5)
        self.assertTrue(results)
        self.assertEqual("DOLIPRANE", results[0]["specialite"])
        self.assertIn("1 G", results[0]["dosage"])
        self.assertTrue(results[0]["source"])

    def test_search_arabic_and_accent_normalization(self):
        self.assertEqual(core.normalize("أَمْوكسِيسيلين"), core.normalize("اموكسيسيلين"))
        self.assertTrue(core.search_catalog("PARACETAMOL", limit=3))

    def test_ingestion_keeps_unknown_values_empty_and_unique_ids(self):
        with core.connect() as conn:
            count, unique_count, missing_epi = conn.execute("SELECT COUNT(*), COUNT(DISTINCT id), SUM(epi='') FROM medications").fetchone()
        self.assertEqual(count, unique_count)
        self.assertEqual(9908, count)
        self.assertEqual(count, missing_epi)


class RequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        core.ensure_database()

    def test_darija_arabizi_strength_and_product(self):
        result = core.interpret_request("3afak wach kayn Doliprane 1000 mg?")
        self.assertEqual("darija_latn", result["language"])
        self.assertEqual("availability_inquiry", result["intent"])
        self.assertEqual("DOLIPRANE", result["medication_name"])
        self.assertIn("1000 mg", result["strength"].lower())

    def test_arabic_and_french(self):
        self.assertEqual("darija_ar", core.interpret_request("واش هاد الدوا كاين؟")["language"])
        french = core.interpret_request("Quel est le prix de Doliprane ?")
        self.assertEqual("fr", french["language"])
        self.assertEqual("price_inquiry", french["intent"])
        self.assertEqual("DOLIPRANE", french["medication_name"])

    def test_unsafe_clinical_question_is_flagged(self):
        result = core.interpret_request("شنو ناخد على الصداع؟")
        self.assertEqual("unsupported_medical_question", result["intent"])
        self.assertTrue(result["safety_message"])

    def test_message_only_uses_confirmed_fields_and_language(self):
        result = core.pharmacy_request({"catalog_id": "563", "strength": "1 G", "form": "COMPRIME", "language": "darija_ar", "location": "Rabat"})
        self.assertIn("DOLIPRANE", result["message"])
        self.assertEqual("Rabat", result["location"])
        self.assertFalse(result["availability_checked"])
        self.assertIn("BOITE DE 8", result["message"])
        with self.assertRaises(ValueError):
            core.pharmacy_request({})
        with self.assertRaises(ValueError):
            core.pharmacy_request({"catalog_id": "unverified", "name": "Fake Medicine"})

    def test_requested_box_count_is_separate_from_package_size(self):
        result = core.interpret_request("Bghit Doliprane 1 G, 2 boites")
        self.assertEqual("2 boites", result["requested_quantity"])
        self.assertEqual("1 G", result["strength"])

    def test_uncertain_match_does_not_claim_calibrated_confidence(self):
        matches = core.match_image_text("DOLIPRANE 500 MG")
        self.assertTrue(matches)
        self.assertIn("matching_score", matches[0])
        self.assertIn("match_evidence", matches[0])
        self.assertEqual("500   MG", matches[0]["dosage"])

    def test_generic_pharmacy_words_do_not_become_a_medicine(self):
        result = core.interpret_request("Je cherche ce médicament en pharmacie.")
        self.assertIsNone(result["medication_name"])
        self.assertTrue(result["needs_clarification"])
        self.assertEqual([], core.search_catalog("DIACURE", limit=3))

    def test_arabic_availability_is_interpreted(self):
        result = core.interpret_request("واش هاد الدوا كاين؟")
        self.assertEqual("availability_inquiry", result["intent"])


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        core.ensure_database()

    def call(self, path, method="GET", body=b"", content_type="application/json"):
        captured = {}
        def start(status, headers):
            captured["status"] = status
            captured["headers"] = headers
        env = {"PATH_INFO": path, "REQUEST_METHOD": method, "QUERY_STRING": "q=Doliprane", "CONTENT_LENGTH": str(len(body)), "CONTENT_TYPE": content_type, "wsgi.input": io.BytesIO(body)}
        data = b"".join(app.app(env, start))
        return captured["status"], json.loads(data) if "json" in dict(captured["headers"]).get("Content-Type", "") else data

    def test_health_and_catalog_api(self):
        status, data = self.call("/api/health")
        self.assertEqual("200 OK", status)
        self.assertEqual(9908, data["records"])
        status, data = self.call("/api/medications")
        self.assertEqual("200 OK", status)
        self.assertTrue(data["items"])

    def test_interpret_api_unicode(self):
        status, data = self.call("/api/interpret", "POST", json.dumps({"text":"واش كاين Doliprane؟"}, ensure_ascii=False).encode())
        self.assertEqual("200 OK", status)
        self.assertEqual("DOLIPRANE", data["interpretation"]["medication_name"])

    def test_interpret_candidates_respect_requested_strength(self):
        status, data = self.call("/api/interpret", "POST", json.dumps({"text":"3afak wach kayn Doliprane 1000 mg?"}).encode())
        self.assertEqual("200 OK", status)
        self.assertTrue(data["candidates"])
        self.assertTrue(all(core._strength_keys(x["dosage"]) & {("mass_mg", 1000.0)} for x in data["candidates"]))

    def test_pharmacy_request_api_requires_and_uses_catalogue_id(self):
        status, data = self.call("/api/pharmacy-request", "POST", json.dumps({"catalog_id":"563","language":"fr"}).encode())
        self.assertEqual("200 OK", status)
        self.assertIn("DOLIPRANE", data["message"])
        self.assertFalse(data["availability_checked"])
        status, data = self.call("/api/pharmacy-request", "POST", json.dumps({"name":"Invented"}).encode())
        self.assertEqual("400 Bad Request", status)

    def test_invalid_image_rejected_and_missing_ocr_graceful(self):
        with self.assertRaises(ValueError):
            core.recognize_image(b"not an image", "bad.jpg")
        try:
            from PIL import Image
            buf = io.BytesIO(); Image.new("RGB", (10, 10), "white").save(buf, format="PNG"); valid_image = buf.getvalue()
        except ImportError:
            valid_image = b"\x89PNG\r\n\x1a\n"
        with patch("dawaling_core.tesseract_engine", return_value=None):
            result = core.recognize_image(valid_image, "tiny.png")
        self.assertFalse(result["ocr_available"])

    def test_local_tesseract_reads_text_from_a_generated_smoke_image(self):
        engine = core.tesseract_engine()
        if not engine:
            self.skipTest("Tesseract is optional and not installed in this environment.")
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            self.skipTest("Pillow is optional and not installed.")
        image = Image.new("RGB", (1200, 360), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 112)
        draw.text((40, 80), "DOLIPRANE 1 G", fill="black", font=font)
        buf = io.BytesIO(); image.save(buf, format="PNG")
        result = core.recognize_image(buf.getvalue(), "smoke.png")
        self.assertTrue(result["ocr_available"])
        self.assertIn("DOLIPRANE", result["extracted_text"].upper())
        self.assertTrue(result["candidates"])

    def test_generic_packaging_words_do_not_generate_product_candidates(self):
        self.assertEqual([], core.match_image_text("ENFANTS CHILDREN"))

    def test_ocr_related_results_include_full_ingredient_catalogue(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is optional and not installed.")
        image = io.BytesIO(); Image.new("RGB", (24, 24), "white").save(image, format="PNG")
        recognized = "Diclo’ ID Diclofenac Sodium 150 mg modified release tablet"

        def fake_tesseract(args, **kwargs):
            if args[1] == "--list-langs":
                return SimpleNamespace(stdout="List of available languages (3):\neng\nfra\nara\n", stderr="", returncode=0)
            return SimpleNamespace(stdout=recognized, stderr="", returncode=0)

        with patch("dawaling_core.tesseract_engine", return_value="/fake/tesseract"), \
             patch("dawaling_core.subprocess.run", side_effect=fake_tesseract):
            result = core.recognize_image(image.getvalue(), "diclofenac.png")

        self.assertEqual([], result["candidates"])  # 150 mg is not in this source export.
        self.assertGreater(len(result["related_candidates"]), 6)
        algirhuma = next(item for item in result["related_candidates"] if item["id"] == "8150")
        self.assertEqual("ALGIRHUMA", algirhuma["specialite"])
        self.assertIn(algirhuma, result["related_preview"])


if __name__ == "__main__":
    unittest.main()
