"""Local Ollama backed conversation for the pharmacy enquiry workflow.

The model extracts what the user wants and what medicine they mean. Product
facts and candidate IDs always come from the local catalogue, never from model
memory. No hosted LLM endpoint is used.
"""
from __future__ import annotations

import json
import os
import re
import ipaddress
import threading
import urllib.error
import urllib.request

import dawaling_core as core

OLLAMA_URL = os.environ.get("DAWALINK_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.environ.get("DAWALINK_LLM_MODEL", "qwen3:1.7b")
INTENTS = {"availability", "price", "find_pharmacy", "product_info", "identify", "medical_advice", "other"}
LANGUAGES = {"fr", "darija_latn", "darija_ar", "ar", "unknown"}
_MODEL_LOCK = threading.Lock()

SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": sorted(INTENTS)},
        "language": {"type": "string", "enum": sorted(LANGUAGES)},
        "medicine_query": {"type": ["string", "null"]},
        "strength": {"type": ["string", "null"]},
        "form": {"type": ["string", "null"]},
        "quantity": {"type": ["string", "null"]},
        "city": {"type": ["string", "null"]},
        "needs_clinical_advice": {"type": "boolean"},
    },
    "required": ["intent", "language", "medicine_query", "strength", "form", "quantity", "city", "needs_clinical_advice"],
}

SYSTEM = """You are a multilingual information extractor for a Moroccan pharmacy enquiry app.
Return only the requested JSON fields. Understand French, Moroccan Darija in Arabic
and Latin/Arabizi, Arabic, and mixed messages. Remember details from earlier user
messages in this conversation. Identify the user's practical goal and medicine name,
strength, form, requested quantity, and city when explicitly stated. Never infer a
medicine name from symptoms. Set needs_clinical_advice=true for symptoms, diagnosis,
which medicine to take, dosage advice, contraindications, pregnancy, or interactions.
Do not answer the user, recommend treatment, invent stock, prices, pharmacies or facts.
Use null for missing details. Keep extracted strings short and copy only what the user
said; do not add explanations."""


def _is_local_url() -> bool:
    from urllib.parse import urlsplit
    host = urlsplit(OLLAMA_URL).hostname or ""
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _request(path: str, payload: dict | None = None, timeout: float = 2.0) -> dict:
    if not _is_local_url():
        raise ConnectionError("Configurez Ollama avec une adresse locale (127.0.0.1).")
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_URL}{path}", data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def status() -> dict:
    try:
        tags = _request("/api/tags", timeout=1.5).get("models", [])
        installed = {item.get("name", "") for item in tags}
        selected = MODEL in installed or any(name.split(":", 1)[0] == MODEL.split(":", 1)[0] for name in installed)
        return {"available": True, "model_ready": selected, "model": MODEL,
                "provider": "Ollama local", "private": True}
    except (OSError, ValueError, urllib.error.URLError):
        return {"available": False, "model_ready": False, "model": MODEL,
                "provider": "Ollama local", "private": True}


def _clean(value, limit=100):
    if not isinstance(value, str):
        return None
    result = " ".join(value.replace("\x00", " ").split())[:limit].strip()
    return result or None


def _needs_clinical_safety(text: str) -> bool:
    """High precision cues for personal medical advice; product enquiries stay usable."""
    n = core.normalize(text)
    patterns = (
        r"\b(?:what|which)\s+(?:medicine|medication|drug|dose|dosage)\b.{0,45}\b(?:should|can|do)\s+i\s+(?:take|use|give)\b",
        r"\bhow\s+much\s+(?:should|can|do)\s+i\s+(?:take|use)\b",
        r"\b(?:should|can)\s+i\s+take\b.{0,45}\b(?:pregnan|interact|side effect)\b",
        r"\b(?:j ai mal|mal de tete|mal au ventre|j ai une douleur|j ai de la fievre|que dois je prendre|quel medicament prendre|quelle dose prendre|quelle posologie)\b",
        r"\b(?:i have|i ve got|having)\s+(?:a\s+)?(?:headache|fever|pain|cough|nausea|rash)\b",
        r"\b(?:chno|ach|ash)\s+(?:nakhod|ndwi|ndir)\b",
        r"\b(?:wach nakhod|nakhod chno|dwa l(?:\s+\w+){0,3})\b",
        r"\b(?:interaction|contre indication|enceinte|grossesse|effet secondaire)\b",
        r"(?:شنو\s*ناخد|اش\s*ناخد|ماذا\s*أ?تناول|ما\s*الجرعة|ما\s*العلاج|بماذا\s*أعالج|هل\s*آخذ)",
        r"(?:عندي|اعاني من).{0,24}(?:صداع|الم|حمى|سخانة|سعال|غثيان|وجع)",
    )
    return any(re.search(pattern, n) for pattern in patterns)


def _ground_slots(slots: dict, text: str) -> dict:
    """Drop model-extracted values that have no textual support."""
    n = core.normalize(text)
    med = slots["medicine_query"]
    useful_tokens = [token for token in core.normalize(med or "").split() if len(token) > 1 and token not in core.STOP]
    text_tokens = [token for token in re.findall(r"[\w]+", n, re.UNICODE) if len(token) > 1]
    grounded = all(token in n or any(core.SequenceMatcher(None, token, observed).ratio() >= .86 for observed in text_tokens) for token in useful_tokens)
    if med and (not useful_tokens or not grounded):
        slots["medicine_query"] = None
    strength_match = re.search(r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|ug|g|ml|ui|iu|%)\b", text, re.I)
    if not strength_match:
        slots["strength"] = None
    elif slots["strength"] and not core._strength_keys(text).intersection(core._strength_keys(slots["strength"])):
        slots["strength"] = None
    if slots["form"]:
        form_words = {
            "tablet": ("tablet", "tablets", "comprime", "comprimé", "حبوب", "قرص", "أقراص"),
            "comprime": ("tablet", "tablets", "comprime", "comprimé", "حبوب", "قرص", "أقراص"),
            "capsule": ("capsule", "capsules", "gelule", "gélule", "كبسولة"),
            "gelule": ("capsule", "capsules", "gelule", "gélule", "كبسولة"),
            "syrup": ("syrup", "sirop", "شراب"),
            "sirop": ("syrup", "sirop", "شراب"),
            "solution": ("solution", "حلول"),
            "injection": ("injection", "حقنة", "حقن"),
            "suppository": ("suppositoire", "suppository", "لبوس"),
            "suppositoire": ("suppositoire", "suppository", "لبوس"),
            "drops": ("drops", "gouttes", "قطرات"),
            "gouttes": ("drops", "gouttes", "قطرات"),
            "sachet": ("sachet", "sachets", "كيس"),
        }
        form_key = core.normalize(slots["form"])
        aliases = form_words.get(form_key)
        if not aliases or not any(core.normalize(alias) in n for alias in aliases):
            slots["form"] = None
    if slots["quantity"] and not re.search(r"\b\d+\s+(?:boites?|boite|boxes?|packs?|paquets?|unit[eé]s?|pieces?|pi[eè]ces?)\b", n):
        slots["quantity"] = None
    city = slots["city"]
    if city and core.normalize(city) not in n:
        slots["city"] = None
    return slots


def _model_extract(user_messages: list[str]) -> dict:
    payload = {
        "model": MODEL,
        "stream": False,
        "format": SCHEMA,
        "think": False,
        "options": {"temperature": 0, "num_predict": 180},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Conversation turns, oldest first:\n" + "\n".join(f"User: {m}" for m in user_messages[-8:])},
        ],
    }
    response = _request("/api/chat", payload, timeout=90)
    content = response.get("message", {}).get("content", "")
    parsed = json.loads(content)
    if not isinstance(parsed, dict) or parsed.get("intent") not in INTENTS:
        raise ValueError("The local model returned an invalid intent.")
    return {
        "intent": parsed["intent"],
        "language": parsed.get("language") if parsed.get("language") in LANGUAGES else "unknown",
        "medicine_query": _clean(parsed.get("medicine_query"), 100),
        "strength": _clean(parsed.get("strength"), 50),
        "form": _clean(parsed.get("form"), 50),
        "quantity": _clean(parsed.get("quantity"), 50),
        "city": _clean(parsed.get("city"), 60),
        "needs_clinical_advice": bool(parsed.get("needs_clinical_advice")),
    }


def _reply(slots: dict, candidates: list[dict]) -> tuple[str, str]:
    language = slots["language"]
    intent = slots["intent"]
    query = slots["medicine_query"]
    if slots["needs_clinical_advice"] or intent == "medical_advice":
        safety = {
            "fr": "Je ne peux pas conseiller un traitement, une dose ou interpréter des symptômes. Demandez conseil à un pharmacien ou à un professionnel de santé.",
            "darija_latn": "Ma n9drch nans7ek b dawa wla dosage. 3afak swel saydali wla tbib.",
            "darija_ar": "ما نقدرش ننصحك بدواء ولا بجرعة. عفاك سول الصيدلي ولا الطبيب.",
            "ar": "لا أستطيع اقتراح علاج أو جرعة. يرجى سؤال الصيدلي أو الطبيب.",
        }.get(language, "Je ne peux pas conseiller un traitement ou une dose. Demandez conseil à un pharmacien ou à un professionnel de santé.")
        return safety, "clinical_safety"

    if intent == "find_pharmacy" and not query:
        text = {
            "fr": "Je n’ai pas d’annuaire ni de position des pharmacies dans cette version. Si vous cherchez à demander un médicament, dites-moi son nom et votre ville ; je préparerai une question à envoyer.",
            "darija_latn": "Ma 3ndich dalil wla localisation dyal pharmacies f had nskha. Ila bghiti tsowel 3la dwa, 3tini smiyto w mdintk bach nwjed lik sou2al tsifto.",
            "darija_ar": "ما عنديش دليل ولا مواقع الصيدليات فهاد النسخة. إلا بغيتي تسول على دواء، عطيني سميتو والمدينة باش نوجد ليك سؤال تصيفطو.",
            "ar": "لا يتوفر في هذه النسخة دليل أو مواقع للصيدليات. إذا أردت السؤال عن دواء، اذكر اسمه ومدينتك لأجهز لك سؤالًا ترسله.",
        }.get(language, "Je n’ai pas d’annuaire des pharmacies dans cette version. Dites-moi le médicament et la ville si vous souhaitez préparer une question.")
        return text, "no_pharmacy_directory"

    if not query:
        prompts = {
            "fr": "D’accord. Quel est le nom du médicament ? Vous pouvez aussi envoyer une photo de la boîte.",
            "darija_latn": "Wakha. Chno smit dawa? T9der ta tsift tswira dyal lboita.",
            "darija_ar": "واخا. شنو سميت الدوا؟ تقدر حتى تصيفط تصويرة ديال العلبة.",
            "ar": "حسنًا، ما اسم الدواء؟ يمكنك أيضًا إرسال صورة العلبة.",
        }
        return prompts.get(language, prompts["fr"]), "ask_medicine"

    if not candidates:
        prompts = {
            "fr": f"Je n’ai pas trouvé de correspondance fiable pour « {query} ». Vérifiez l’orthographe ou envoyez une photo nette de la boîte.",
            "darija_latn": f"Ma lqitch match mti9a l « {query} ». T2ekked men smiya wla sift tswira wad7a dyal lboita.",
            "darija_ar": f"ما لقيتش تطابق موثوق مع « {query} ». تأكد من الاسم ولا صيفط تصويرة واضحة ديال العلبة.",
            "ar": f"لم أجد تطابقًا موثوقًا للاسم « {query} ». تحقق من الكتابة أو أرسل صورة واضحة للعلبة.",
        }
        return prompts.get(language, prompts["fr"]), "no_match"

    if len(candidates) > 1:
        prompts = {
            "fr": f"J’ai trouvé {len(candidates)} fiches proches pour « {query} ». Choisissez celle qui correspond exactement au dosage et à la forme sur votre boîte.",
            "darija_latn": f"Lqit {len(candidates)} fiches qrabin l « {query} ». Khtar li kaytabeq l dosage w chkel li f lboita.",
            "darija_ar": f"لقيت {len(candidates)} fichات قراب لـ « {query} ». اختار اللي كيطابق الجرعة والشكل اللي فالعلبة.",
            "ar": f"وجدت {len(candidates)} سجلات قريبة من « {query} ». اختر ما يطابق الجرعة والشكل المكتوبين على العلبة.",
        }
        return prompts.get(language, prompts["fr"]), "choose_product"

    product = candidates[0]
    if intent == "find_pharmacy":
        text = {
            "fr": "Cette version ne dispose pas d’annuaire de pharmacies. Je peux préparer une question à envoyer à une pharmacie de votre ville.",
            "darija_latn": "Had nskha ma fiha-ch dalil dyal pharmacies. N9der nwjed lik sou2al tsifto l chi pharmacie f mdintk.",
            "darija_ar": "هاد النسخة ما فيهاش دليل الصيدليات. نقدر نوجد ليك سؤال تصيفطو لشي صيدلية فمدينتك.",
            "ar": "لا تتضمن هذه النسخة دليلًا للصيدليات. يمكنني تجهيز سؤال ترسله إلى صيدلية في مدينتك.",
        }.get(language, "Cette version ne dispose pas d’annuaire de pharmacies. Je peux préparer une question à envoyer à une pharmacie de votre ville.")
    elif intent == "product_info":
        ingredient = product.get("substance_active") or "non renseignée dans la fiche"
        text = {
            "fr": f"La fiche du catalogue indique : {ingredient}. Vérifiez cette information sur la boîte ou avec un pharmacien. Je peux aussi préparer une demande sur la disponibilité.",
            "darija_latn": f"F fiche catalogue kayban: {ingredient}. T2ekked men lboita wla swel saydali. N9der nwjed lik sou2al 3la wach kayn.",
            "darija_ar": f"فالدليل كاين: {ingredient}. تأكد من العلبة ولا سول الصيدلي. نقدر نوجد ليك سؤال على التوفر.",
            "ar": f"تذكر بطاقة الدواء في الدليل: {ingredient}. تحقق من العبوة أو اسأل الصيدلي. يمكنني أيضًا تجهيز سؤال عن التوفر.",
        }.get(language, f"La fiche du catalogue indique : {ingredient}. Vérifiez cette information sur la boîte ou avec un pharmacien.")
    elif intent == "price":
        price = product.get("ppv") or "non indiqué dans cette fiche"
        if core.normalize(price) in {"sans ppv", "dh", "sans prix", "non renseigne"}:
            price = "non indiqué dans cette fiche"
        text = {
            "fr": f"La fiche indique {price} comme prix catalogue. Ce montant n’est pas vérifié aujourd’hui ; demandez confirmation à la pharmacie.",
            "darija_latn": f"F fiche kayban taman catalogue: {price}. Had taman ma mverifyach lyoum; 3afak t2ekked m3a pharmacie.",
            "darija_ar": f"ف fiche كيبان ثمن الكاتالوغ: {price}. هاد الثمن ما متأكدش منو اليوم؛ عفاك تأكد مع الصيدلية.",
            "ar": f"يظهر في الدليل سعر قدره {price}. لم يتم التحقق من السعر اليوم؛ يرجى التأكد من الصيدلية.",
        }.get(language, f"La fiche indique {price} comme prix catalogue, à confirmer auprès de la pharmacie.")
    else:
        text = {
            "fr": "La fiche est sélectionnée. Le catalogue ne donne pas le stock en temps réel. Vous pouvez préparer une question à envoyer vous-même à une pharmacie.",
            "darija_latn": "Tkhtarat lfiche. Catalogue ma kaybeyench stock daba. T9der twjed sou2al tsifto b rask l pharmacie.",
            "darija_ar": "تختارت fiche. الكاتالوغ ما كيبينش التوفر دابا. تقدر توجد سؤال وتصيفطو براسك للصيدلية.",
            "ar": "تم اختيار السجل. الدليل لا يعرض المخزون الفعلي. يمكنك تجهيز سؤال وإرساله بنفسك إلى الصيدلية.",
        }.get(language, "La fiche est sélectionnée. Le catalogue ne donne pas le stock en temps réel. Vous pouvez préparer une question à envoyer vous-même à une pharmacie.")
    return text, "prepare_enquiry"


def converse(messages: list) -> dict:
    user_messages = [
        _clean(item.get("content"), 500)
        for item in messages[-12:]
        if isinstance(item, dict) and item.get("role") == "user"
    ]
    user_messages = [item for item in user_messages if item]
    if not user_messages:
        raise ValueError("Écrivez votre question pour commencer.")
    if sum(map(len, user_messages)) > 2400:
        raise ValueError("La conversation est trop longue. Commencez une nouvelle demande.")
    llm_status = status()
    if not llm_status["available"]:
        raise ConnectionError("Le modèle local n’est pas démarré. Lancez Ollama puis rechargez la page.")
    if not llm_status["model_ready"]:
        raise FileNotFoundError(f"Le modèle {MODEL} n’est pas installé. Lancez: ollama pull {MODEL}")

    with _MODEL_LOCK:
        slots = _ground_slots(_model_extract(user_messages), " ".join(user_messages))
    # A precise local guard overrides the model on clear personal medical requests.
    # Its broad classification is deliberately not used for ordinary product questions.
    if _needs_clinical_safety(" ".join(user_messages)):
        slots["needs_clinical_advice"] = True
        slots["intent"] = "medical_advice"
        slots["medicine_query"] = None
        slots["strength"] = None
        slots["form"] = None
    else:
        slots["needs_clinical_advice"] = False
        n = core.normalize(" ".join(user_messages))
        explicit_price = any(cue in n for cue in ("prix", "price", "taman", "ch7al", "بشحال", "ثمن"))
        explicit_availability = any(cue in n for cue in ("disponible", "availability", "available", "stock", "kayn", "kayna", "wach", "عندكم", "متوفر", "كاين"))
        if explicit_price:
            slots["intent"] = "price"
        elif explicit_availability:
            slots["intent"] = "availability"
        elif slots["intent"] == "medical_advice":
            slots["intent"] = "identify" if slots["medicine_query"] else "other"
    detected_language = core._detect_language(" ".join(user_messages))
    if detected_language != "unknown":
        slots["language"] = detected_language
    query_parts = [slots["medicine_query"], slots["strength"], slots["form"]]
    query = " ".join(part for part in query_parts if part)
    candidates = core.search_catalog(query, limit=8) if slots["medicine_query"] else []
    desired_strength = core._strength_keys(slots["strength"] or "")
    if desired_strength:
        candidates = [item for item in candidates if desired_strength.issubset(core._strength_keys(item.get("dosage", "")))]
    if slots["form"] and candidates:
        form = core.normalize(slots["form"])
        aliases = {"tablet": ("comprime", "tablet", "حبوب", "قرص"), "comprime": ("comprime", "tablet", "حبوب", "قرص"), "capsule": ("capsule", "gelule", "كبسولة"), "gelule": ("capsule", "gelule", "كبسولة"), "syrup": ("sirop", "syrup", "شراب"), "sirop": ("sirop", "syrup", "شراب"), "solution": ("solution",), "injection": ("injection", "حقنة"), "suppository": ("suppositoire", "suppository", "لبوس"), "suppositoire": ("suppositoire", "suppository", "لبوس"), "drops": ("gouttes", "drops", "قطرات"), "gouttes": ("gouttes", "drops", "قطرات"), "sachet": ("sachet", "كيس")}
        form_tokens = aliases.get(form, (form,))
        candidates = [item for item in candidates if any(core.normalize(token) in core.normalize(item.get("forme", "")) for token in form_tokens)]
    candidates = candidates[:4]
    reply, next_step = _reply(slots, candidates)
    return {
        "reply": reply,
        "slots": slots,
        "candidates": candidates,
        "next_step": next_step,
        "model": MODEL,
        "llm_used": True,
        "catalogue_price_note": "Le prix est une valeur du catalogue, pas un prix vérifié aujourd’hui.",
    }
