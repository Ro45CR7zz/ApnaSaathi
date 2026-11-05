"""Rule-based understanding for English, Hindi and Hinglish.

Used when Gemini is unavailable, and to fill fields Gemini left empty. Deliberately conservative:
it only extracts what it can recognise with confidence.
"""
from __future__ import annotations

import re
from typing import Optional

from app.advisor.slots import ProfileUpdate
from app.catalogue.loader import load_reference
from app.recommender.segment import match_business_type

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "che": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "सात": 7, "आठ": 8,
    "नौ": 9, "दस": 10, "बीस": 20, "पचास": 50,
}
CITY_ALIASES = {
    "bangalore": "Bengaluru", "bengaluru": "Bengaluru", "बेंगलुरु": "Bengaluru", "बैंगलोर": "Bengaluru",
    "bombay": "Mumbai", "मुंबई": "Mumbai", "calcutta": "Kolkata", "कोलकाता": "Kolkata",
    "vizag": "Visakhapatnam", "विशाखापत्तनम": "Visakhapatnam", "mysore": "Mysuru", "मैसूर": "Mysuru",
    "baroda": "Vadodara", "वडोदरा": "Vadodara", "cochin": "Kochi", "कोच्चि": "Kochi",
    "दिल्ली": "Delhi", "new delhi": "Delhi", "हैदराबाद": "Hyderabad", "चेन्नई": "Chennai", "madras": "Chennai",
    "पुणे": "Pune", "poona": "Pune", "अहमदाबाद": "Ahmedabad", "लुधियाना": "Ludhiana", "इंदौर": "Indore",
    "नागपुर": "Nagpur", "लखनऊ": "Lucknow", "भोपाल": "Bhopal", "जयपुर": "Jaipur", "कोयंबटूर": "Coimbatore",
    "नासिक": "Nashik", "पटना": "Patna", "सूरत": "Surat",
}

STAFF = r"(?:staff|employees?|people|persons?|workers?|log|लोग|कर्मचारी|स्टाफ|आदमी|जन)"
SITES = r"(?:shops?|branch(?:es)?|outlets?|sites?|locations?|stores?|offices?|clinics?|restaurants?|salons?|pharmac(?:y|ies)|gyms?|hotels?|schools?|labs?|centres?|centers?|units?|factor(?:y|ies)|godowns?|warehouses?|दुकान(?:ें)?|ब्रांच|शाखा(?:एं|ओं)?|जगह(?:ें)?)"
NUM = r"(\d{1,4}|" + "|".join(sorted(map(re.escape, NUMBER_WORDS), key=len, reverse=True)) + r")"

NEED_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("cctv", ("cctv", "camera", "कैमरा", "सीसीटीवी")),
    ("billing_upi", ("upi", "billing", "बिलिंग", "pos", "payment", "पेमेंट", "qr", "बिल ")),
    ("guest_wifi", ("wifi", "wi-fi", "वाईफाई", "वाई-फाई")),
    ("whatsapp_customers", ("whatsapp", "व्हाट्सएप", "व्हाट्सऐप", "catalogue", "कैटलॉग")),
    ("sms_alerts", ("sms", "एसएमएस", "bulk message")),
    ("website", ("website", "वेबसाइट", "online presence", "domain")),
    ("email_office", ("email", "e-mail", "ईमेल", "office suite", "documents", "google workspace", "microsoft 365")),
    ("backup_files", ("data backup", "file backup", "cloud backup", "बैकअप")),
    ("security", ("virus", "antivirus", "ransomware", "hacking", "hack", "cyber", "firewall", "फ़ायरवॉल", "वायरस", "साइबर")),
    ("uptime_backup", ("internet goes down", "net goes down", "failover", "backup internet", "net band",
                       "नेट बंद", "internet down", "outage", "uptime")),
    ("central_management", ("central", "sd-wan", "sdwan", "one dashboard", "manage all")),
    ("static_ip", ("static ip", "fixed ip", "स्टैटिक")),
    ("cloud_calling", ("ivr", "call recording", "calling system", "call centre", "call center", "landline", "कॉलिंग")),
    ("toll_free", ("toll free", "toll-free", "1800", "टोल फ्री", "टोल-फ्री")),
    ("machines_iot", ("machine", "मशीन", "iot", "sensor", "energy use")),
    ("vehicles", ("vehicle", "truck", "fleet", "gps", "गाड़ी", "गाड़ियाँ", "ट्रक", "delivery van")),
    ("mobile_lines", ("sim", "सिम", "mobile line", "mobile connection", "phone line", "postpaid", "मोबाइल नंबर",
                      "mobile number", "business number")),
    ("internet", ("internet", "broadband", "इंटरनेट", "नेट", "fibre", "fiber", "wifi connection")),
]
OUT_OF_SCOPE = ("dth", "tv channel", "डीटीएच", "loan", "लोन", "insurance policy", "credit card")
HUMAN = ("talk to a person", "talk to someone", "human", "agent", "call me", "call back", "callback",
         "insaan", "इंसान", "किसी से बात", "executive", "salesperson", "representative")
YES = ("yes", "yeah", "yep", "haan", "han", "ha ", "ji", "हाँ", "हां", "जी", "है", "hai", "registered")
NO = ("no", "nahi", "nahin", "नहीं", "नही", "not registered", "don't have", "dont have", "na ")
NO_MORE = ("that's all", "thats all", "nothing else", "bas", "बस", "only internet", "sirf internet",
           "सिर्फ इंटरनेट", "kuch nahi", "कुछ नहीं", "no more", "done")


def _num(token: str) -> Optional[int]:
    token = token.translate(DEVANAGARI_DIGITS).lower()
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token)


def _has_devanagari(text: str) -> bool:
    return bool(re.search(r"[ऀ-ॿ]", text))


def _find_city(text: str) -> Optional[str]:
    t = text.lower()
    for alias, city in CITY_ALIASES.items():
        if alias in t:
            return city
    for city in load_reference()["cities"]:
        if re.search(r"\b" + re.escape(city.lower()) + r"\b", t):
            return city
    return None


NOT_CITY = {"my", "our", "the", "a", "an", "shop", "store", "business", "office", "india", "town", "city",
            "market", "area", "total", "all", "one", "it", "english", "hindi"}


def _guess_unlisted_city(text: str, expecting: Optional[str]) -> Optional[str]:
    """Cities outside the dataset: 'in Shimla', or a short answer right after we asked for the city."""
    m = re.search(r"\b(?:in|at|from)\s+([A-Z][a-zA-Z]{2,})", text)
    if m and m.group(1).lower() not in NOT_CITY and not match_business_type(m.group(1)):
        return m.group(1)
    if expecting == "city":
        cand = re.sub(r"[^\w\s\u0900-\u097F]", " ", text).strip()
        cand = re.sub(r"\s*(mein|में|me|city|शहर)$", "", cand, flags=re.I).strip()
        if cand and len(cand.split()) <= 3 and not re.search(r"\d", cand) and not match_business_type(cand):
            return cand.title() if cand.isascii() else cand
    return None


def _contains(t: str, words: tuple[str, ...]) -> bool:
    padded = f" {t} "
    return any((f" {w.strip()} " in padded) if w.isascii() and len(w.strip()) <= 3 else (w in padded) for w in words)


def extract(text: str, expecting: Optional[str] = None) -> ProfileUpdate:
    """Extract facts from one message. `expecting` is the slot the Advisor just asked about."""
    raw = text.translate(DEVANAGARI_DIGITS)
    t = re.sub(r"[^\w\s\-ऀ-ॿ]", " ", raw.lower())
    t = re.sub(r"\s+", " ", t).strip()
    u: dict = {"language": "hi" if _has_devanagari(text) else None}

    if _contains(t, HUMAN):
        u["intent"] = "human"
    elif _contains(t, OUT_OF_SCOPE):
        u["intent"] = "out_of_scope"

    bt = match_business_type(t)
    if bt and not (expecting == "needs" and bt[0] in ("Retail shop", "Office")):
        u["business_type"], u["segment"] = bt

    city = _find_city(t)
    if not city:
        city = _guess_unlisted_city(text, expecting)
    if city:
        u["city"] = city

    m = re.search(NUM + r"\s*" + STAFF, t) or re.search(STAFF + r"\s*(?:of|is|are|=|:)?\s*" + NUM, t)
    if m:
        u["employees"] = _num(m.group(1))
    elif re.search(r"\b(just me|only me|alone|akela|अकेला|अकेले|सिर्फ मैं)\b", t):
        u["employees"] = 1

    m = re.search(NUM + r"\s*" + SITES, t)
    if m:
        u["sites"] = _num(m.group(1))
    elif re.search(r"\b(single|one|ek)\s+(shop|store|dukaan|location|office)\b|एक दुकान|एक ही", t):
        u["sites"] = 1

    m = re.search(NUM + r"\s*(?:sims?|सिम|mobile lines?|phone lines?|connections?)", t)
    if m:
        u["mobile_lines"] = _num(m.group(1))
    m = re.search(NUM + r"\s*(?:cameras?|cctv|कैमरे|कैमरा)", t)
    if m:
        u["cameras"] = _num(m.group(1))
    m = re.search(NUM + r"\s*(?:vehicles?|trucks?|गाड़ियाँ|गाड़ी|ट्रक|vans?)", t)
    if m:
        u["vehicles"] = _num(m.group(1))
    m = re.search(NUM + r"\s*(?:counters?|काउंटर)", t)
    if m:
        u["counters"] = _num(m.group(1))
    m = re.search(NUM + r"\s*(?:machines?|मशीन(?:ें)?|devices?|computers?|pcs?|laptops?)", t)
    if m:
        u["devices"] = _num(m.group(1))

    # GSTIN yes/no: explicit mentions, or a plain yes/no right after we asked.
    if re.search(r"(no|without|nahi|नहीं|नही|not)\s*(a\s*)?(gst|जीएसटी)|(gst|जीएसटी)\s*(number\s*)?(nahi|नहीं|नही|not|no)", t):
        u["has_gstin"] = False
    elif re.search(r"(gst|जीएसटी)\s*(registered|hai|है|number hai|registration hai)|have (a )?gst|(gst|जीएसटी) (है|hai)", t):
        u["has_gstin"] = True
    elif expecting == "has_gstin":
        if _contains(t, NO):
            u["has_gstin"] = False
        elif _contains(t, YES):
            u["has_gstin"] = True

    if re.search(r"(no|nahi|नहीं) (fibre|fiber|फ़ाइबर|फाइबर)|(fibre|fiber|फाइबर) (not available|nahi|नहीं)", t):
        u["fibre_available"] = False

    needs = []
    for tag, words in NEED_KEYWORDS:
        if tag == "mobile_lines" and u.get("business_type") == "Mobile repair shop" and "sim" not in t:
            continue
        if _contains(t, words):
            needs.append(tag)
    # A stated quantity implies the need ("3 sims", "4 cameras", "2 trucks").
    for qty_key, tag in (("mobile_lines", "mobile_lines"), ("cameras", "cctv"), ("vehicles", "vehicles"),
                         ("counters", "billing_upi")):
        if u.get(qty_key) and tag not in needs:
            needs.append(tag)
    if "cctv" in needs and "security" in needs and not re.search(r"virus|ransom|cyber|hack|firewall|वायरस", t):
        needs.remove("security")
    u["needs"] = needs
    if expecting == "needs" and (_contains(t, NO_MORE) or (not needs and _contains(t, NO))):
        u["no_more_needs"] = True

    # A bare number answers the question we just asked.
    if expecting in ("employees", "sites"):
        m = re.fullmatch(NUM, t)
        if m and expecting not in u:
            u[expecting] = _num(m.group(1))

    asks = "?" in text or re.match(r"^(what|how|why|which|can|does|is|kya|kaise|क्या|कैसे|कौन)\b", t)
    if asks and u.get("intent") is None and \
            not any(k in u for k in ("business_type", "city", "employees", "sites", "has_gstin")):
        u["intent"] = "question"
        u["user_question"] = text.strip()[:200]
        u["needs"] = []  # asking about a product is not the same as asking for it
        u.pop("no_more_needs", None)

    return ProfileUpdate(**{k: v for k, v in u.items() if v is not None})
