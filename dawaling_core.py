"""Local catalogue, request parsing, matching and optional OCR for DawaLink."""
from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import unicodedata
from io import BytesIO
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "moroccan_medications.csv"
DB_PATH = ROOT / "pharmacy.db"
FIELDS = ("id", "specialite", "substance_active", "dosage", "forme", "presentation", "epi", "statut", "ppv", "ph")
DATA_SOURCE = "repository:moroccan_medications.csv (AMMPS web export; original import date not recorded)"


def tesseract_engine() -> str | None:
    """Find system Tesseract or the optional project-local Linux install."""
    configured = os.environ.get("DAWALINK_TESSERACT")
    if configured:
        return configured
    system_engine = shutil.which("tesseract")
    if system_engine:
        return system_engine
    local_engine = ROOT / ".local" / "ocr" / "usr" / "bin" / "tesseract"
    return str(local_engine) if local_engine.is_file() else None


def tesseract_environment() -> dict[str, str]:
    """Set paths for the optional extracted local package without shell setup."""
    env = os.environ.copy()
    local_root = ROOT / ".local" / "ocr" / "usr"
    local_lib = local_root / "lib" / "x86_64-linux-gnu"
    local_data = local_root / "share" / "tesseract-ocr" / "5" / "tessdata"
    if local_lib.is_dir():
        env["LD_LIBRARY_PATH"] = str(local_lib) + (":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    if local_data.is_dir():
        env["TESSDATA_PREFIX"] = str(local_data)
    return env


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or "").casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.replace("ـ", "")
    value = re.sub(r"[أإآٱ]", "ا", value).replace("ى", "ي").replace("ة", "ه")
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def read_csv(path: Path = CSV_PATH) -> tuple[list[dict], str]:
    raw = path.read_bytes()
    encoding = "utf-8-sig"
    try:
        raw.decode(encoding)
    except UnicodeDecodeError:
        encoding = "cp1252"
    text = raw.decode(encoding)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], encoding
    aliases = {normalize(k).replace(" ", "_"): k for k in reader.fieldnames}
    # Resolve each canonical column once. Doing the Unicode normalization for
    # every field in every row made ingestion repeat the same regex work ~100k
    # times for this catalogue.
    source_fields = {
        field: aliases.get(normalize(field).replace(" ", "_"), field)
        for field in FIELDS
    }
    rows = []
    for row in reader:
        item = {field: (row.get(source_key) or "").strip()
                for field, source_key in source_fields.items()}
        if item["id"] and item["specialite"]:
            rows.append(item)
    return rows, encoding


def ensure_database(force: bool = False, csv_path: Path = CSV_PATH, db_path: Path = DB_PATH) -> dict:
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing medication catalogue: {csv_path.name}")
    if db_path.exists() and not force and db_path.stat().st_mtime >= csv_path.stat().st_mtime:
        with closing(sqlite3.connect(db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM medications").fetchone()[0]
            fts = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='medication_fts'").fetchone() is not None
        rows, encoding = read_csv(csv_path)
        return {**quality_report(rows, encoding, fts), "records": count, "reused_database": True}
    rows, encoding = read_csv(csv_path)
    imported_at = datetime.now(timezone.utc).isoformat()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_suffix(db_path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    with closing(sqlite3.connect(tmp_path)) as conn:
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("""CREATE TABLE medications (
            id TEXT PRIMARY KEY, specialite TEXT NOT NULL, substance_active TEXT, dosage TEXT,
            forme TEXT, presentation TEXT, epi TEXT, statut TEXT, ppv TEXT, ph TEXT,
            brand_key TEXT NOT NULL, substance_key TEXT NOT NULL, source TEXT NOT NULL, imported_at TEXT NOT NULL
        )""")
        conn.executemany("INSERT INTO medications VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            (*[row[f] for f in FIELDS], normalize(row["specialite"]), normalize(row["substance_active"]), DATA_SOURCE, imported_at)
            for row in rows
        ])
        conn.execute("CREATE INDEX idx_med_brand ON medications(brand_key)")
        conn.execute("CREATE INDEX idx_med_substance ON medications(substance_key)")
        conn.execute("CREATE INDEX idx_med_form ON medications(forme)")
        try:
            conn.execute("CREATE VIRTUAL TABLE medication_fts USING fts5(id UNINDEXED, specialite, substance_active, dosage, forme, presentation, tokenize='unicode61 remove_diacritics 2')")
            conn.executemany("INSERT INTO medication_fts VALUES (?,?,?,?,?,?)", [(r["id"], r["specialite"], r["substance_active"], r["dosage"], r["forme"], r["presentation"]) for r in rows])
            fts = True
        except sqlite3.OperationalError:
            fts = False
        conn.commit()
    tmp_path.replace(db_path)
    report = quality_report(rows, encoding, fts)
    return {**report, "reused_database": False}


def quality_report(rows: list[dict], encoding: str, fts: bool = True) -> dict:
    n = len(rows)
    unavailable = {"ppv": {"DH", "SANS PPV"}, "ph": {"DH", "SANS PH"}}
    missing = {key: sum(not (r.get(key) or "").strip() or (r.get(key) or "").strip().upper() in unavailable.get(key, set()) for r in rows) for key in FIELDS}
    return {
        "source_file": CSV_PATH.name,
        "source": DATA_SOURCE,
        "source_record_date": None,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "encoding": encoding,
        "source_rows": n,
        "usable_rows": n,
        "duplicate_ids_removed": 0,
        "duplicate_ids_in_source": n - len({r["id"] for r in rows}),
        "unique_brand_values": len({r["specialite"] for r in rows}),
        "missing_values": missing,
        "fts5_enabled": fts,
        "limitations": ["Source export date was not retained in the repository.", "EPI is blank for all current rows.", "Blank fields are preserved; no values are inferred."],
    }


@contextmanager
def connect(db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def serialize(row: sqlite3.Row | dict) -> dict:
    result = {f: row[f] or "" for f in FIELDS}
    result.update({"source": row["source"] if "source" in row.keys() else DATA_SOURCE,
                   "imported_at": row["imported_at"] if "imported_at" in row.keys() else ""})
    return result


def _score(query: str, row: sqlite3.Row) -> float:
    q = normalize(query)
    brand, ingredient = row["brand_key"], row["substance_key"]
    if not q:
        return 0
    query_strength = _strength_keys(query)
    product_strength = _strength_keys(row["dosage"])
    text_terms = [t for t in q.split() if not t.isdigit() and t not in {"mg", "mcg", "g", "ml", "ui", "iu"}]
    if q == brand or q == ingredient:
        score = 1.0
    elif q in brand or q in ingredient:
        score = 0.93
    elif text_terms and all(token in brand or token in ingredient for token in text_terms):
        score = 0.83
    else:
        score = max(SequenceMatcher(None, " ".join(text_terms) or q, brand).ratio(), SequenceMatcher(None, " ".join(text_terms) or q, ingredient).ratio() * .95)
    if query_strength:
        if query_strength & product_strength:
            score += .16
        elif product_strength:
            score -= .48
    return max(0.0, min(1.0, score))


def _strength_keys(text: str) -> set[tuple[str, float]]:
    keys = set()
    number = r"\d+(?:(?:[., ]\d{3})+)?(?:[.,]\d+)?"
    for value, unit in re.findall(rf"({number})\s*(mg|mcg|µg|g|ml|ui|iu|%)", text or "", re.I):
        compact = value.replace(" ", "")
        if compact.count(",") + compact.count(".") > 1:
            compact = compact.replace(".", "").replace(",", "")
        elif "," in compact or "." in compact:
            sep = "," if "," in compact else "."
            left, right = compact.rsplit(sep, 1)
            if len(right) == 3 and left.isdigit() and int(left) > 0:
                compact = left + right
            else:
                compact = left + "." + right
        amount = float(compact)
        unit = unit.casefold()
        if unit == "g":
            unit, amount = "mass_mg", amount * 1000
        elif unit == "mg":
            unit = "mass_mg"
        elif unit in ("mcg", "µg"):
            unit, amount = "mass_mg", amount / 1000
        elif unit in ("ui", "iu"):
            unit = "unit"
        keys.add((unit, round(amount, 3)))
    return keys


def search_catalog(query: str = "", form: str = "", status: str = "", limit: int = 12, db_path: Path = DB_PATH) -> list[dict]:
    query = str(query or "").strip()[:200]
    limit = max(1, min(10000, int(limit)))
    with connect(db_path) as conn:
        where, params = [], []
        if form:
            where.append("forme LIKE ?")
            params.append(f"%{str(form)[:80]}%")
        if status:
            where.append("statut LIKE ?")
            params.append(f"%{str(status)[:80]}%")
        clause = " WHERE " + " AND ".join(where) if where else ""
        if not query:
            rows = conn.execute("SELECT * FROM medications" + clause + " ORDER BY specialite LIMIT ?", [*params, limit]).fetchall()
            return [serialize(r) for r in rows]
        rows = []
        qnorm = normalize(query)
        try:
            terms = " AND ".join('"' + token.replace('"', '') + '"*' for token in qnorm.split())
            if terms:
                rows = conn.execute("SELECT m.* FROM medication_fts f JOIN medications m ON m.id=f.id WHERE medication_fts MATCH ?" + (" AND " + " AND ".join(where) if where else "") + " LIMIT 10000", [terms, *params]).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if not rows:
            tokens = [t for t in query.split() if len(normalize(t)) > 1]
            if tokens:
                conds = []
                values = []
                for token in tokens:
                    conds.append("(brand_key LIKE ? OR substance_key LIKE ? OR dosage LIKE ? OR forme LIKE ?)")
                    values.extend([f"%{normalize(token)}%"] * 4)
                rows = conn.execute("SELECT * FROM medications WHERE " + " AND ".join(conds) + (" AND " + " AND ".join(where) if where else "") + " LIMIT 10000", [*values, *params]).fetchall()
        if not rows and len(query) >= 4:
            rows = conn.execute("SELECT * FROM medications" + clause + " LIMIT 10000", params).fetchall()
        ranked = sorted(((_score(query, r), r) for r in rows), key=lambda p: (-p[0], p[1]["specialite"], p[1]["dosage"]))
        # Keep loose lexical lookalikes out of medicine identification results.
        return [{**serialize(r), "matching_score": round(score, 3)} for score, r in ranked[:limit] if score >= .78]


STOP = set("bghit bghina n3ref nعرف wach wash kayn kayna f fin taman prix ch7al 3afak salam hada had hadchi dwa dawa medicament je cherche cherchez cherche veux voudrais trouver est ce que avez vous disponible svp le la les du de un une des a au pour dyal pharmacie pharmacies médicament medicaments boite boîte comprimé comprime mg g ml rabat casablanca بغيت بغينا نعرف واش كاين كاينة الدوا دواء الدواء ثمن عفاك فين عندكم هذا هاد من ليا شي الدواء واش أعاني عندي مرض شنو".split())
INTENTS = {
    "price_inquiry": ("prix", "taman", "thaman", "ch7al", "ثمن", "بشحال"),
    "availability_inquiry": ("disponible", "availability", "kayn", "kayna", "wach kayn", "واش كاين", "كاين", "عندكم", "stock", "avez", "avez vous"),
    "pharmacy_location_inquiry": ("fin", "where", "ou trouver", "pharmacie proche", "فين", "قريب"),
    "product_information": ("composition", "substance", "contains", "contient", "شنو فيه", "اشنو فيه", "information"),
}
UNSUPPORTED = ("dose", "dosage pour moi", "interaction", "pregnant", "enceinte", "حامل", "جرعة", "نعطي لطفل", "symptom", "diagnose", "علاج", "نعالج", "صداع", "ناخد", "شنو ناخد")


def _detect_language(text: str) -> str:
    if re.search(r"[\u0600-\u06ff]", text):
        return "darija_ar" if any(x in text for x in ("واش", "بغيت", "عفاك", "الدوا", "فين", "شنو", "عندي")) else "ar"
    n = normalize(text)
    if any(x in n.split() for x in ("bghit", "bghina", "wach", "kayn", "n3ref", "dwa", "dawa", "fin")):
        return "darija_latn"
    if re.search(r"[àâçéèêëîïôùûüÿœæ]", text, re.I) or any(w in n.split() for w in ("je", "cherche", "medicament", "pharmacie", "prix", "est")):
        return "fr"
    return "unknown"


def interpret_request(text: str, db_path: Path = DB_PATH) -> dict:
    text = str(text or "").strip()[:2000]
    n = normalize(text)
    intent = "medication_identification"
    for label, cues in INTENTS.items():
        if any(normalize(cue) in n for cue in cues):
            intent = label
            break
    if any(normalize(cue) in n for cue in UNSUPPORTED):
        intent = "unsupported_medical_question"
    strength_match = re.search(r"\b(\d+(?:[.,]\d+)?\s?(?:mg|mcg|g|ml|µg|ui|iu|%)(?:\s*/\s*\d+(?:[.,]\d+)?\s?(?:ml|g))?)\b", text, re.I)
    form = next((f for f in ("comprimé", "comprime", "tablet", "capsule", "gélule", "gelule", "sirop", "solution", "injection", "suppositoire", "sachet", "قطرات", "أقراص") if normalize(f) in n), None)
    qty_match = re.search(r"\b(?:(?:x|quantite|quantity|nombre|bghit|je veux)(?:\s+\w+){0,5}\s+)?(\d+)\s+(boites?|packets?|units?|pieces?)\b", n)
    requested_quantity = f"{qty_match.group(1)} {qty_match.group(2)}" if qty_match else None

    # Prefer the longest exact catalogue brand mention. This is deterministic and avoids
    # turning arbitrary sentence words into a medicine name.
    with connect(db_path) as conn:
        brands = conn.execute("SELECT DISTINCT specialite, brand_key FROM medications ORDER BY LENGTH(brand_key) DESC").fetchall()
    med_name = None
    for brand, brand_key in brands:
        if len(brand_key) >= 3 and re.search(r"(?<!\w)" + re.escape(brand_key) + r"(?!\w)", n):
            med_name = brand
            break
    if not med_name:
        words = [w for w in re.findall(r"[\w]+", text, re.UNICODE) if normalize(w) not in STOP and not (strength_match and normalize(w) in normalize(strength_match.group())) and len(w) >= 3]
        candidate = " ".join(words[:5])
        matches = search_catalog(candidate, limit=1, db_path=db_path) if candidate else []
        if matches and matches[0].get("matching_score", 0) >= .78:
            med_name = matches[0]["specialite"]
    location_match = re.search(r"(?:\bf\b|\bà\b|\ba\b|\bin\b|فين)\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ '-]{1,35})", text)
    location = location_match.group(1).strip(" ,?.") if location_match else None
    missing = ["medication_name"] if not med_name and intent != "unsupported_medical_question" else []
    return {"language": _detect_language(text), "intent": intent, "medication_name": med_name,
            "strength": strength_match.group(1).strip() if strength_match else None, "form": form,
            "requested_quantity": requested_quantity, "location": location,
            "missing_information": missing, "needs_clarification": bool(missing),
            "safety_message": "This tool cannot assess symptoms, treatment, interactions, or personal dosage. Please ask a pharmacist or clinician." if intent == "unsupported_medical_question" else None}


def match_image_text(text: str, limit: int = 5, db_path: Path = DB_PATH) -> list[dict]:
    cleaned = re.sub(r"[^\w\s/.,%-]+", " ", text or "")
    generic = {"enfants", "children", "infants", "adulte", "adultes", "adult", "anti", "infiammator", "infiammatoire", "inflammatoire", "inflammatoires", "rhumatism", "rhumatisme", "rhumatismal", "rhumatismale", "sodium", "sodique", "chloride", "chlorure", "potassium", "potassique", "calcium", "magnesium", "modified", "dified", "release", "prolonged", "liberation", "retard", "comprimé", "comprime", "comprimés", "capsule", "capsules", "sachet", "sachets", "sirop", "solution", "suppositoire", "suppositoires", "pharma", "pharmaceutical", "dosage", "composition", "ingredients", "ingredient", "notice", "tablets", "tablet", "tabl", "tabiet", "tabiets"}
    strength_units = {"mg", "mcg", "µg", "ug", "g", "ml", "ui", "iu"}
    ocr_name_tokens = {normalize(token) for token in re.findall(r"[\w]+", cleaned, re.UNICODE)}
    ocr_name_tokens = {token for token in ocr_name_tokens
                       if len(token) >= 3 and token not in generic and token not in strength_units
                       and not token.isdigit()}
    def informative(value: str) -> str:
        # Keep short units attached to the OCR'd number: dropping “mg” here
        # turns a specific “BRAND 500 MG” query into a brand-only search and
        # can rank a different catalogue strength ahead of the correct one.
        return " ".join(token for token in re.findall(r"[\w]+", value, re.UNICODE)
                        if (len(normalize(token)) >= 3 or normalize(token) in strength_units)
                        and normalize(token) not in generic)
    candidates: dict[str, dict] = {}
    # Ingredient searches can return dozens of valid medicines. Asking the
    # general catalogue search for only the UI result limit silently discarded
    # a visible product brand such as DICLOFENAC MAPHAR at rank 12.
    retrieval_limit = max(100, min(250, int(limit) * 20))
    for line in cleaned.splitlines():
        line = informative(line)
        if len(normalize(line)) >= 3:
            for item in search_catalog(line[:100], limit=retrieval_limit, db_path=db_path):
                candidates.setdefault(item["id"], item)
    if not candidates:
        # Search readable brand/ingredient tokens directly before launching
        # fuzzy phrase scans. This retains related records even when their
        # strength conflicts with the package and avoids rescanning the full
        # 9,908-row catalogue for noisy phrases such as label copy.
        named_tokens = {normalize(token) for token in re.findall(r"[\w]+", informative(cleaned), re.UNICODE)
                        if len(normalize(token)) >= 5 and not normalize(token).isdigit()}
        if named_tokens:
            with connect(db_path) as conn:
                for token in named_tokens:
                    rows = conn.execute(
                        "SELECT * FROM medications WHERE brand_key LIKE ? OR substance_key LIKE ? LIMIT 500",
                        (f"%{token}%", f"%{token}%")).fetchall()
                    for row in rows:
                        item = serialize(row)
                        item["matching_score"] = round(_score(token, row), 3)
                        candidates.setdefault(item["id"], item)
    if not candidates:
        tokens = re.findall(r"[\w]+", informative(cleaned))
        # Avoid spending a separate full catalogue fuzzy scan on every noisy
        # OCR token window. Product names are usually one to three words.
        phrases = [" ".join(tokens[i:j]) for i in range(len(tokens))
                   for j in range(i + 1, min(len(tokens), i + 3) + 1)]
        for phrase in sorted(set(phrases), key=lambda value: (-len(value.split()), -len(value)))[:8]:
            if len(normalize(phrase)) < 4:
                continue
            for item in search_catalog(phrase, limit=retrieval_limit, db_path=db_path):
                candidates.setdefault(item["id"], item)
    dosage_terms = _strength_keys(cleaned)
    ranked = []
    for item in candidates.values():
        score = float(item.get("matching_score", .0))
        evidence = ["name or ingredient text similarity"]
        brand_tokens = set(normalize(item["specialite"]).split())
        brand_signal = len(brand_tokens & ocr_name_tokens)
        if brand_signal:
            evidence.append("visible OCR text agrees with product brand")
        product_doses = _strength_keys(item["dosage"])
        if dosage_terms:
            if dosage_terms & product_doses:
                score += .08; evidence.append("extracted strength agrees")
            elif product_doses:
                score -= .35; evidence.append("strength conflicts or does not appear in OCR text")
            elif item["dosage"]:
                score -= .35; evidence.append("catalogue dosage cannot be compared with the OCR strength")
        if item["forme"] and normalize(item["forme"]) in normalize(cleaned):
            score += .04; evidence.append("formulation text agrees")
        item["matching_score"] = round(max(0, min(1, score)), 3)
        item["match_evidence"] = evidence
        item["_brand_signal"] = brand_signal
        ranked.append(item)
    ranked.sort(key=lambda x: (-x["_brand_signal"], -x["matching_score"], x["specialite"], x["dosage"]))
    for item in ranked:
        item.pop("_brand_signal", None)
    return ranked[:limit]


def recognize_image(data: bytes, filename: str, db_path: Path = DB_PATH) -> dict:
    if not data or len(data) > 8 * 1024 * 1024:
        raise ValueError("Image must be between 1 byte and 8 MB.")
    mime = None
    suffix = ".img"
    if data.startswith(b"\xff\xd8\xff"):
        mime, suffix = "image/jpeg", ".jpg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime, suffix = "image/png", ".png"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        mime, suffix = "image/webp", ".webp"
    if not mime:
        raise ValueError("Unsupported image. Upload a JPEG, PNG, or WebP medicine photograph.")
    image_obj = None
    try:
        from PIL import Image, ImageOps, ImageFilter
        image_obj = Image.open(BytesIO(data))
        if image_obj.width * image_obj.height > 30_000_000:
            raise ValueError("Image dimensions exceed the 30 megapixel safety limit.")
        image_obj = ImageOps.exif_transpose(image_obj).convert("RGB")
        image_obj = ImageOps.autocontrast(ImageOps.grayscale(image_obj))
        if max(image_obj.size) < 1800:
            ratio = 1800 / max(image_obj.size)
            image_obj = image_obj.resize((int(image_obj.width * ratio), int(image_obj.height * ratio)), Image.Resampling.LANCZOS)
        image_obj = image_obj.filter(ImageFilter.SHARPEN)
        prepared = BytesIO()
        image_obj.save(prepared, format="PNG")
        image_data = prepared.getvalue()
    except ImportError:
        image_data = data
        suffix = suffix
    except ValueError:
        raise
    except Exception:
        raise ValueError("The uploaded file is not a readable image.")
    engine = tesseract_engine()
    if not engine:
        return {"ocr_available": False, "message": "Local OCR is unavailable. Install Tesseract OCR and its French/English language data, then restart the app.", "extracted_text": "", "candidates": []}
    with tempfile.NamedTemporaryFile(suffix=".png" if image_data is not data else suffix) as image:
        image.write(image_data); image.flush()
        lang = "eng+fra+ara"
        env = tesseract_environment()
        langs = subprocess.run([engine, "--list-langs"], capture_output=True, text=True, timeout=10, env=env).stdout
        available = set(langs.splitlines()[1:])
        lang = "+".join(x for x in ("eng", "fra", "ara") if x in available) or "eng"
        outputs = []
        output_matches = []
        used_languages = set()

        def read_text(path: str, language: str, psm: str, timeout: int = 15) -> bool:
            """Run one local segmentation pass and keep its text and matches."""
            result = subprocess.run([engine, path, "stdout", "-l", language, "--psm", psm],
                                    capture_output=True, text=True, timeout=timeout,
                                    check=False, env=env)
            used_languages.update(language.split("+"))
            text = result.stdout.strip()
            if result.returncode == 0 and text and all(normalize(text) != normalize(previous) for previous in outputs):
                outputs.append(text)
                output_matches.append(match_image_text(text, limit=40, db_path=db_path))
            return bool(output_matches and any(item["matching_score"] >= .82 for item in output_matches[-1]))

        try:
            first_plausible = read_text(image.name, lang, "6", timeout=30)
        except subprocess.TimeoutExpired:
            raise ValueError("OCR took too long. Try a smaller or clearer image.")
        # Medicine packaging uses separated labels, logos and tiny text. PSM 6
        # assumes a uniform text block; retry as sparse text if it found no
        # catalogue-backed candidate, even when it did read generic packaging.
        # A Latin-only pass also avoids the Arabic model diluting French/brand
        # recognition on bilingual boxes.
        if not first_plausible:
            latin_lang = "+".join(x for x in ("eng", "fra") if x in available) or lang
            try:
                first_plausible = read_text(image.name, latin_lang, "11")
            except subprocess.TimeoutExpired:
                first_plausible = False

        # The pasted Diclo OCR was reading dosage/usage copy but not the name.
        # If full-frame passes still have no catalogue-backed name, OCR
        # overlapping close-up tiles so a product occupying only part of a
        # phone photo is enlarged before recognition. These passes stay local.
        if not first_plausible and image_obj is not None and hasattr(image_obj, "crop"):
            width, height = image_obj.size
            x_mid, y_mid = width // 2, height // 2
            overlap_x, overlap_y = width // 8, height // 8
            boxes = [
                (0, 0, min(width, x_mid + overlap_x), min(height, y_mid + overlap_y)),
                (max(0, x_mid - overlap_x), 0, width, min(height, y_mid + overlap_y)),
                (0, max(0, y_mid - overlap_y), min(width, x_mid + overlap_x), height),
                (max(0, x_mid - overlap_x), max(0, y_mid - overlap_y), width, height),
            ]
            for box in boxes:
                tile = image_obj.crop(box)
                if max(tile.size) < 1500:
                    scale = 1500 / max(tile.size)
                    tile = tile.resize((int(tile.width * scale), int(tile.height * scale)), Image.Resampling.LANCZOS)
                with tempfile.NamedTemporaryFile(suffix=".png") as crop_file:
                    tile.save(crop_file, format="PNG"); crop_file.flush()
                    try:
                        first_plausible = read_text(crop_file.name, latin_lang, "11", timeout=12)
                    except subprocess.TimeoutExpired:
                        first_plausible = False
                if first_plausible:
                    break
    if not outputs:
        return {"ocr_available": True, "message": "The image could not be read. Try a sharper, well-lit photograph with the product name visible.", "extracted_text": "", "candidates": []}
    # Merge candidate evidence from both page-segmentation passes. Keep the
    # strongest read per catalogue ID while retaining the best readable OCR
    # transcript for display.
    by_id = {}
    for candidates in output_matches:
        for item in candidates:
            old = by_id.get(item["id"])
            if old is None or item["matching_score"] > old["matching_score"]:
                by_id[item["id"]] = item
    matches = sorted(by_id.values(), key=lambda x: (-x["matching_score"], x["specialite"], x["dosage"]))
    def output_quality(index: int) -> tuple[float, int]:
        score = max((item["matching_score"] for item in output_matches[index]), default=0)
        words = {normalize(word) for word in re.findall(r"[\w]+", outputs[index], re.UNICODE)
                 if len(normalize(word)) >= 4 and not normalize(word).isdigit()}
        return score, len(words)
    best_index = max(range(len(outputs)), key=output_quality)
    best_output = outputs[best_index]
    extracted = best_output
    # Keep weak lookalikes out of the product list; spelling similarity is not identity.
    near_matches = matches
    matches = [item for item in matches if item["matching_score"] >= .82]
    related_candidates = []
    related_preview = []
    needs_confirmation = not matches or matches[0]["matching_score"] < .90 or (len(matches) > 1 and matches[0]["matching_score"] - matches[1]["matching_score"] < .10)
    message = "OCR text matched against the local catalogue." if matches else "The product name was not read clearly enough to match the catalogue. Try a closer, sharper photo of the medicine name and strength."
    if not matches:
        # Explain an exact-strength miss when OCR did read an ingredient and
        # dosage but the supplied catalogue only has other strengths. Never
        # turn those other strengths into positive candidates.
        read_strengths = _strength_keys(extracted)
        recognized_ingredient = None
        for item in near_matches:
            substance_tokens = [token for token in normalize(item["substance_active"]).split()
                                if len(token) >= 6]
            if any(re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)", normalize(extracted))
                   for token in substance_tokens):
                recognized_ingredient = next((token for token in substance_tokens
                                              if re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)", normalize(extracted))), None)
                if recognized_ingredient:
                    break
        if read_strengths and recognized_ingredient:
            with connect(db_path) as conn:
                ingredient_rows = conn.execute(
                    "SELECT id,specialite,substance_active,dosage,forme,presentation,ppv,ph,statut,epi,source,imported_at "
                    "FROM medications WHERE substance_key LIKE ?",
                    (f"%{recognized_ingredient}%",)).fetchall()
                available_doses = [row["dosage"] for row in ingredient_rows]
            exact_strength_exists = any(read_strengths & _strength_keys(dose) for dose in available_doses)
            if not exact_strength_exists:
                strength_label = next((m.group(0).upper() for m in re.finditer(
                    r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|ug|g|ml|ui|iu)\b", extracted, re.I)), "")
                # Keep related local records visible so users can inspect what
                # the catalogue contains. These are clearly separated from
                # exact candidates and cannot be selected as a confirmed match.
                release_words = {"modified", "release", "prolonged", "liberation", "prolongee", "lp", "retard", "sr", "er"}
                wants_release = bool(release_words & set(normalize(extracted).split()))
                related = []
                for row in ingredient_rows:
                    item = serialize(row)
                    item_doses = _strength_keys(item["dosage"])
                    if read_strengths & item_doses:
                        continue
                    row_words = set(normalize(item["specialite"] + " " + item["forme"]).split())
                    release_rank = int(wants_release and bool(release_words & row_words))
                    distance = min((abs(requested[1] - dose[1]) for requested in read_strengths
                                    for dose in item_doses if requested[0] == dose[0]), default=10**9)
                    item["related_reason"] = "Different strength or release form; verify against the package"
                    related.append((release_rank, distance, item))
                related.sort(key=lambda entry: (-entry[0], entry[1], entry[2]["specialite"], entry[2]["dosage"]))
                related_candidates = [item for _, _, item in related]
                # Show a small but strength-diverse sample first; keep every
                # local record available in the expandable full list.
                seen_doses = set()
                for _, _, item in related:
                    dose_key = tuple(sorted(_strength_keys(item["dosage"]))) or (normalize(item["dosage"]),)
                    if dose_key not in seen_doses:
                        related_preview.append(item); seen_doses.add(dose_key)
                    if len(related_preview) == 6:
                        break
                if len(related_preview) < 6:
                    preview_ids = {item["id"] for item in related_preview}
                    related_preview.extend([item for item in related_candidates
                                            if item["id"] not in preview_ids][:6-len(related_preview)])
                message = (f"J’ai lu {recognized_ingredient.upper()} {strength_label}, mais ce dosage n’existe pas dans le catalogue local. "
                           f"Voici les fiches {recognized_ingredient.upper()} présentes dans le catalogue; elles ne correspondent pas exactement au dosage lu.")
    return {"ocr_available": True, "message": message, "extracted_text": extracted, "candidates": matches, "related_candidates": related_candidates, "related_preview": related_preview, "needs_confirmation": needs_confirmation, "ocr_languages": sorted(used_languages)}


def pharmacy_request(payload: dict) -> dict:
    record_id = str(payload.get("catalog_id") or "").strip()
    with connect() as conn:
        row = conn.execute("SELECT * FROM medications WHERE id=?", (record_id,)).fetchone() if record_id else None
    if not row:
        raise ValueError("Select a real catalogue product before generating a pharmacy enquiry.")
    name = row["specialite"]
    strength = str(payload.get("strength") if payload.get("strength") is not None else row["dosage"] or "").strip()[:60]
    form = str(payload.get("form") if payload.get("form") is not None else row["forme"] or "").strip()[:80]
    presentation = str(payload.get("presentation") if payload.get("presentation") is not None else row["presentation"] or "").strip()[:100]
    quantity = str(payload.get("requested_quantity") or "").strip()[:60]
    location = str(payload.get("location") or "").strip()[:100]
    language = payload.get("language") if payload.get("language") in ("fr", "darija_latn", "darija_ar") else "fr"
    question_type = payload.get("question_type") if payload.get("question_type") in ("availability", "price", "both") else "both"
    details = " ".join(x for x in (name, strength, form, presentation) if x)
    if not details:
        raise ValueError("Confirm a medicine name before generating a pharmacy enquiry.")
    quantity_phrase = f" ({quantity})" if quantity else ""
    location_fr = f" à {location}" if location else ""
    location_darija = f" f {location}" if location else ""
    messages = {
        "fr": {
            "availability": f"Bonjour, avez-vous {details}{quantity_phrase}{location_fr} ? Merci.",
            "price": f"Bonjour, quel est le prix de {details}{quantity_phrase}{location_fr} ? Merci.",
            "both": f"Bonjour, avez-vous {details}{quantity_phrase}{location_fr} ? Si oui, quel est son prix ? Merci.",
        },
        "darija_latn": {
            "availability": f"Salam, 3afak wach 3andkom {details}{quantity_phrase}{location_darija}? Chokran.",
            "price": f"Salam, 3afak ch7al taman dyal {details}{quantity_phrase}{location_darija}? Chokran.",
            "both": f"Salam, 3afak wach 3andkom {details}{quantity_phrase}{location_darija}? Ila kayn, ch7al taman? Chokran.",
        },
        "darija_ar": {
            "availability": f"السلام عليكم، عفاكم واش متوفر عندكم {details}{quantity_phrase}{f' ف {location}' if location else ''}؟ شكراً.",
            "price": f"السلام عليكم، شحال ثمن {details}{quantity_phrase}{f' ف {location}' if location else ''}؟ شكراً.",
            "both": f"السلام عليكم، عفاكم واش متوفر عندكم {details}{quantity_phrase}{f' ف {location}' if location else ''}؟ إذا كان متوفراً، شحال الثمن؟ شكراً.",
        },
    }
    intent_name = "availability_inquiry" if question_type == "availability" else "price_inquiry" if question_type == "price" else "availability_and_price_inquiry"
    return {"intent": intent_name, "medication": {"catalog_id": record_id, "name": name, "strength": strength or None, "form": form or None, "presentation": presentation or None}, "requested_quantity": quantity or None, "location": location or None, "message_language": language, "message": messages[language][question_type], "availability_checked": False}
