"""DawaLink local web/API server. Run: python3 app.py"""
from __future__ import annotations

import json
import sqlite3
import sys
import os
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn

import dawaling_core as core
import assistant_service
import pharmacy_directory

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"


class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def response(start, status: str, body: bytes, content_type: str, headers=()):
    start(status, [("Content-Type", content_type), ("Content-Length", str(len(body))), ("X-Content-Type-Options", "nosniff"), *headers])
    return [body]


def json_response(start, payload, status="200 OK"):
    return response(start, status, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8", (("Cache-Control", "no-store"),))


def body_json(environ, max_size=20000):
    length = int(environ.get("CONTENT_LENGTH") or 0)
    if length < 0 or length > max_size:
        raise OverflowError("Request body is too large.")
    raw = environ["wsgi.input"].read(length)
    payload = json.loads(raw or b"{}")
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    return payload


def multipart_file(environ):
    length = int(environ.get("CONTENT_LENGTH") or 0)
    if length < 1 or length > 8 * 1024 * 1024 + 65536:
        raise OverflowError("Image upload must not exceed 8 MB.")
    content_type = environ.get("CONTENT_TYPE", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise ValueError("Send an image as multipart/form-data using the field 'image'.")
    raw = environ["wsgi.input"].read(length)
    message = BytesParser(policy=policy.default).parsebytes((f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode() + raw)
    for part in message.iter_parts():
        if part.get_param("name", header="content-disposition") == "image":
            return part.get_payload(decode=True) or b"", part.get_filename() or "upload"
    raise ValueError("Image file is required in field 'image'.")


def interpret_response(text):
    parsed = core.interpret_request(text)
    query = " ".join(str(x) for x in (parsed["medication_name"], parsed["strength"], parsed["form"]) if x)
    matches = core.search_catalog(query, limit=5) if parsed["medication_name"] else []
    return {"interpretation": parsed, "candidates": matches}


def app(environ, start_response):
    path, method = environ.get("PATH_INFO", "/"), environ.get("REQUEST_METHOD", "GET")
    params = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
    try:
        if path == "/api/health" and method == "GET":
            with core.connect() as conn:
                count = conn.execute("SELECT COUNT(*) FROM medications").fetchone()[0]
            return json_response(start_response, {"ok": True, "product": "DawaLink", "records": count, "ocr_available": core.tesseract_engine() is not None, "catalogue_export_date": None, "source_file_modified_at": datetime.fromtimestamp(core.CSV_PATH.stat().st_mtime, timezone.utc).isoformat()})
        if path == "/api/assistant/status" and method == "GET":
            return json_response(start_response, assistant_service.status())
        if path == "/api/medications" and method == "GET":
            q = params.get("q", params.get("query", [""]))[0]
            try:
                limit = min(50, max(1, int(params.get("per_page", params.get("limit", ["20"]))[0])))
                page = max(1, int(params.get("page", ["1"])[0]))
            except ValueError:
                return json_response(start_response, {"error": "page and per_page must be integers."}, "400 Bad Request")
            start = (page - 1) * limit
            if not q:
                where, values = [], []
                for field in ("form", "status"):
                    value = params.get(field, [""])[0].strip()
                    if value:
                        column = "forme" if field == "form" else "statut"
                        where.append(f"{column} LIKE ?")
                        values.append(f"%{value[:80]}%")
                clause = " WHERE " + " AND ".join(where) if where else ""
                with core.connect() as conn:
                    total = conn.execute("SELECT COUNT(*) FROM medications" + clause, values).fetchone()[0]
                    rows = conn.execute("SELECT * FROM medications" + clause + " ORDER BY specialite COLLATE NOCASE LIMIT ? OFFSET ?", [*values, limit, start]).fetchall()
                items = [core.serialize(r) for r in rows]
                return json_response(start_response, {"items": items, "total": total, "page": page, "per_page": limit})
            items = core.search_catalog(q, params.get("form", [""])[0], params.get("status", [""])[0], 10000)
            total = len(items)
            return json_response(start_response, {"items": items[start:start + limit], "total": total, "page": page, "per_page": limit})
        if path.startswith("/api/medications/") and method == "GET":
            record_id = path.rsplit("/", 1)[-1]
            with core.connect() as conn:
                row = conn.execute("SELECT * FROM medications WHERE id = ?", (record_id,)).fetchone()
            return json_response(start_response, core.serialize(row) if row else {"error": "Medication not found."}, "200 OK" if row else "404 Not Found")
        if path == "/api/interpret" and method == "POST":
            payload = body_json(environ)
            text = str(payload.get("text", "")).strip()
            if not text:
                return json_response(start_response, {"error": "Text is required."}, "400 Bad Request")
            return json_response(start_response, interpret_response(text))
        if path == "/api/assistant/message" and method == "POST":
            payload = body_json(environ, max_size=12000)
            messages = payload.get("messages")
            if not isinstance(messages, list):
                return json_response(start_response, {"error": "messages must be a list."}, "400 Bad Request")
            return json_response(start_response, assistant_service.converse(messages))
        if path == "/api/recognize" and method == "POST":
            data, filename = multipart_file(environ)
            return json_response(start_response, core.recognize_image(data, filename))
        if path == "/api/pharmacy-request" and method == "POST":
            return json_response(start_response, core.pharmacy_request(body_json(environ)))
        if path == "/api/pharmacies/nearby" and method == "POST":
            return json_response(start_response, pharmacy_directory.nearby_pharmacies(body_json(environ, max_size=5000)))
        if path == "/api/chat" and method == "POST":
            payload = body_json(environ)
            text = str(payload.get("message", "")).strip()
            if not text:
                return json_response(start_response, {"error": "Message is required."}, "400 Bad Request")
            result = interpret_response(text)
            parsed = result["interpretation"]
            if parsed["safety_message"]:
                answer = parsed["safety_message"]
            elif result["candidates"]:
                rows = result["candidates"]
                answer = "Catalogue matches (please confirm the exact product):\n" + "\n".join(f"{x['specialite']} — {x['dosage']} — {x['forme']} (catalogue ID {x['id']})" for x in rows[:3]) + "\nCatalogue records do not show current pharmacy stock."
            elif parsed["needs_clarification"]:
                answer = "Which medicine do you mean? Send its name or upload a clear box photo."
            else:
                answer = "I could not find a reliable catalogue match. Please check the spelling or ask a pharmacist."
            return json_response(start_response, {"answer": answer, "interpretation": parsed, "candidates": result["candidates"]})
        if path == "/api/export" and method == "GET":
            items = core.search_catalog(params.get("q", [""])[0], limit=10000)
            import csv, io
            stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=core.FIELDS); writer.writeheader()
            writer.writerows([{f: item[f] for f in core.FIELDS} for item in items])
            return response(start_response, "200 OK", stream.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", (("Content-Disposition", "attachment; filename=medications.csv"),))
        if path in ("/", "/index.html") and method == "GET":
            return response(start_response, "200 OK", (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8", (("Cache-Control", "no-cache"),))
        if path in ("/app.js", "/styles.css") and method == "GET":
            kind = "application/javascript" if path.endswith(".js") else "text/css"
            return response(start_response, "200 OK", (STATIC / path[1:]).read_bytes(), kind + "; charset=utf-8", (("Cache-Control", "no-cache"),))
        if path == "/nearby.css" and method == "GET":
            return response(start_response, "200 OK", (STATIC / "nearby.css").read_bytes(), "text/css; charset=utf-8", (("Cache-Control", "no-cache"),))
        return json_response(start_response, {"error": "Not found."}, "404 Not Found")
    except OverflowError as error:
        return json_response(start_response, {"error": str(error)}, "413 Payload Too Large")
    except (ConnectionError, FileNotFoundError) as error:
        return json_response(start_response, {"error": str(error)}, "503 Service Unavailable")
    except TimeoutError:
        return json_response(start_response, {"error": "The local model took too long. Try again or use catalogue search."}, "504 Gateway Timeout")
    except OSError:
        return json_response(start_response, {"error": "Ollama is not responding on its local address. Check that `ollama serve` is running."}, "503 Service Unavailable")
    except (ValueError, json.JSONDecodeError) as error:
        return json_response(start_response, {"error": str(error) or "Invalid request."}, "400 Bad Request")
    except Exception as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        return json_response(start_response, {"error": "The local application encountered an error."}, "500 Internal Server Error")


if __name__ == "__main__":
    result = core.ensure_database()
    print(f"DawaLink ready: http://127.0.0.1:8000 ({result['records']} catalogue records)")
    make_server("127.0.0.1", 8000, app, server_class=ThreadedWSGIServer).serve_forever()
