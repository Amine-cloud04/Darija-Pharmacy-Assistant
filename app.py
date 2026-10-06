"""Darija Pharmacy Assistant — a local, catalog-grounded web application.

Run: python3 app.py
Then open http://127.0.0.1:8000
"""
from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "moroccan_medications.csv"
DB_PATH = ROOT / "pharmacy.db"
STATIC = ROOT / "static"
FIELDS = ("id", "specialite", "substance_active", "dosage", "forme", "presentation", "epi", "statut", "ppv", "ph")


def price_number(value: str | None) -> float | None:
    if not value:
        return None
    # AMMPS exports both 250,00 and 4.303.00 formatting.
    raw = re.sub(r"[^0-9,.]", "", value)
    if not raw:
        return None
    if raw.count(".") > 1:
        raw = raw.replace(".", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif raw.count(".") == 1 and len(raw.rsplit(".", 1)[1]) != 2:
        raw = raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return None


def ensure_database() -> None:
    """Build an indexed local database when the CSV is newer than it."""
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Missing medicine catalog: {CSV_PATH.name}")
    if DB_PATH.exists() and DB_PATH.stat().st_mtime >= CSV_PATH.stat().st_mtime:
        return
    with sqlite3.connect(DB_PATH) as conn, CSV_PATH.open(encoding="utf-8-sig", newline="") as source:
        conn.execute("DROP TABLE IF EXISTS medications")
        conn.execute("""CREATE TABLE medications (
            id TEXT PRIMARY KEY, specialite TEXT, substance_active TEXT, dosage TEXT,
            forme TEXT, presentation TEXT, epi TEXT, statut TEXT, ppv TEXT, ph TEXT,
            ppv_value REAL, ph_value REAL
        )""")
        rows = []
        for item in csv.DictReader(source):
            values = [item.get(field, "").strip() for field in FIELDS]
            rows.append((*values, price_number(item.get("ppv")), price_number(item.get("ph"))))
        conn.executemany(
            "INSERT OR REPLACE INTO medications VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows
        )
        conn.execute("CREATE INDEX idx_med_name ON medications(specialite COLLATE NOCASE)")
        conn.execute("CREATE INDEX idx_med_substance ON medications(substance_active COLLATE NOCASE)")
        conn.execute("CREATE INDEX idx_med_status ON medications(statut COLLATE NOCASE)")


def connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def serialize(row: sqlite3.Row) -> dict:
    return {field: row[field] or "" for field in FIELDS}


def search(params: dict[str, list[str]]) -> tuple[list[dict], int, int, int]:
    q = params.get("q", [""])[0].strip()
    ingredient = params.get("ingredient", [""])[0].strip()
    form = params.get("form", [""])[0].strip()
    status = params.get("status", [""])[0].strip()
    try:
        page = max(1, int(params.get("page", ["1"])[0]))
        per_page = min(50, max(1, int(params.get("per_page", ["20"])[0])))
    except ValueError:
        page, per_page = 1, 20
    where, values = [], []
    if q:
        tokens = [t for t in re.split(r"\s+", q) if len(t) > 1]
        for token in tokens:
            where.append("(specialite LIKE ? OR substance_active LIKE ? OR dosage LIKE ?)")
            values.extend([f"%{token}%"] * 3)
    if ingredient:
        where.append("substance_active LIKE ?")
        values.append(f"%{ingredient}%")
    if form:
        where.append("forme LIKE ?")
        values.append(f"%{form}%")
    if status:
        where.append("statut LIKE ?")
        values.append(f"%{status}%")
    clause = " WHERE " + " AND ".join(where) if where else ""
    with connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM medications" + clause, values).fetchone()[0]
        records = conn.execute(
            "SELECT * FROM medications" + clause + " ORDER BY specialite COLLATE NOCASE LIMIT ? OFFSET ?",
            [*values, per_page, (page - 1) * per_page],
        ).fetchall()
    return [serialize(r) for r in records], total, page, per_page


def best_matches(text: str, limit: int = 3) -> list[dict]:
    # Test progressively shorter meaningful phrases, then use token search.
    cleaned = re.sub(r"[^\wÀ-ÿ-]+", " ", text.upper()).strip()
    candidates = [cleaned]
    stop_words = {"EST", "CEST", "C", "QUOI", "POUR", "AVEC", "DANS", "THE", "AND", "LES", "DES", "UNE", "UN", "MON", "MA", "DU", "DE", "LA", "LE", "DAWA", "MEDICAMENT"}
    words = [w for w in cleaned.split() if len(w) >= 3 and w not in stop_words]
    candidates.extend(
        " ".join(words[i:j])
        for i in range(len(words))
        for j in range(i + 1, min(len(words), i + 3) + 1)
    )
    with connection() as conn:
        for candidate in candidates:
            if len(candidate) < 3:
                continue
            rows = conn.execute(
                "SELECT * FROM medications WHERE specialite LIKE ? OR substance_active LIKE ? "
                "ORDER BY CASE WHEN specialite = ? THEN 0 ELSE 1 END, specialite LIMIT ?",
                (f"%{candidate}%", f"%{candidate}%", candidate, limit),
            ).fetchall()
            if rows:
                return [serialize(r) for r in rows]
    return []


def chat_reply(message: str) -> dict:
    normalized = message.casefold()
    urgent = ("urgence", "emergency", "allerg", "respir", "chest pain", "douleur poitrine", "suicide")
    if any(term in normalized for term in urgent):
        return {"answer": "Ila kayn dy9 nfass, wja3 f s-sder, 7assassiya qwiya, wla chi 7ala mosta3jala: 3ayet l الإسعاف / sir l-mosta3jal daba. Ma n9drch n3awwad l-isti3jal b chat.", "matches": []}
    matches = best_matches(message)
    if matches:
        lines = []
        for med in matches:
            facts = [med["specialite"]]
            if med["substance_active"]:
                facts.append(f"substance active: {med['substance_active']}")
            if med["dosage"]:
                facts.append(med["dosage"])
            if med["ppv"]:
                facts.append(f"PPV: {med['ppv']}")
            if med["statut"]:
                facts.append(med["statut"])
            lines.append(" — ".join(facts))
        return {
            "answer": "L9it had l-ma3lomat f catalogue AMMPS:\n" + "\n".join(lines) +
                      "\n\nHadchi maشي wasfa wla tashkhis. T2akked m3a saydali/tabib 9bl ma tbda, tbdel, wla t7بس ay dawa.",
            "matches": matches,
        }
    return {
        "answer": "N9dr n9elleb lik f catalogue b smit dawa wla substance active (b7al: `Doliprane`, `paracetamol`, `Augmentin`). Ma n9drch n3ti tashkhis, dose personnelle, wla ta2kid dyal interaction; hadchi khasso saydali wla tabib.",
        "matches": [],
    }


def response(start, status: str, body: bytes, content_type: str, headers=()):
    start(status, [("Content-Type", content_type), ("Content-Length", str(len(body))), *headers])
    return [body]


def json_response(start, payload, status="200 OK"):
    return response(start, status, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8", (("Cache-Control", "no-store"),))


def app(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    params = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
    try:
        if path == "/api/health" and method == "GET":
            with connection() as conn:
                count = conn.execute("SELECT COUNT(*) FROM medications").fetchone()[0]
            return json_response(start_response, {"ok": True, "records": count, "updated": datetime.fromtimestamp(CSV_PATH.stat().st_mtime, timezone.utc).isoformat()})
        if path == "/api/medications" and method == "GET":
            items, total, page, per_page = search(params)
            return json_response(start_response, {"items": items, "total": total, "page": page, "per_page": per_page})
        if path.startswith("/api/medications/") and method == "GET":
            record_id = path.rsplit("/", 1)[-1]
            with connection() as conn:
                row = conn.execute("SELECT * FROM medications WHERE id = ?", (record_id,)).fetchone()
            return json_response(start_response, serialize(row) if row else {"error": "Not found"}, "200 OK" if row else "404 Not Found")
        if path == "/api/export" and method == "GET":
            items, _, _, _ = search({**params, "page": ["1"], "per_page": ["50"]})
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader(); writer.writerows(items)
            return response(start_response, "200 OK", stream.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", (("Content-Disposition", "attachment; filename=medications.csv"),))
        if path == "/api/chat" and method == "POST":
            length = int(environ.get("CONTENT_LENGTH") or 0)
            if length > 20_000:
                return json_response(start_response, {"error": "Message too long"}, "413 Payload Too Large")
            payload = json.loads(environ["wsgi.input"].read(length) or b"{}")
            message = str(payload.get("message", "")).strip()
            if not message:
                return json_response(start_response, {"error": "Message is required"}, "400 Bad Request")
            return json_response(start_response, chat_reply(message))
        if path == "/" or path == "/index.html":
            return response(start_response, "200 OK", (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path in ("/app.js", "/styles.css"):
            content_type = "application/javascript; charset=utf-8" if path.endswith("js") else "text/css; charset=utf-8"
            return response(start_response, "200 OK", (STATIC / path[1:]).read_bytes(), content_type)
        return json_response(start_response, {"error": "Not found"}, "404 Not Found")
    except (ValueError, json.JSONDecodeError):
        return json_response(start_response, {"error": "Invalid request"}, "400 Bad Request")
    except Exception as error:  # Errors stay server-side; avoid exposing internals to users.
        print(f"ERROR: {error}", file=sys.stderr)
        return json_response(start_response, {"error": "Server error"}, "500 Internal Server Error")


if __name__ == "__main__":
    ensure_database()
    print("Darija Pharmacy Assistant: http://127.0.0.1:8000")
    make_server("127.0.0.1", 8000, app).serve_forever()
