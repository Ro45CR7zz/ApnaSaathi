"""Advisor conversation: slot filling in English/Hindi, then a recommendation.

Flow per message: redact personal data -> understand (Gemini, else rules; rules also fill gaps)
-> merge into slots -> handle intent -> ask the next missing question, or recommend.
"""
from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel

from app.advisor import nlu_rules
from app.advisor.llm import LLM, LLMUnavailable, get_llm, safe_text
from app.advisor.redact import redact
from app.advisor.slots import ProfileUpdate, Slots, merge, sanitise
from app.catalogue.display import business_label
from app.catalogue.loader import load_catalogue
from app.recommender.engine import Recommendation, recommend

log = logging.getLogger("apnasaathi.advisor")
MAX_TURNS_BEFORE_FORM = 8
GENERIC_TYPES = {"Retail shop", "Office", "Manufacturing unit", "Clinic"}


class Chip(BaseModel):
    label: str
    value: str


QUESTIONS: dict[str, dict] = {
    "business_type": {
        "en": "What kind of business do you run?",
        "hi": "आप कौन-सा बिज़नेस चलाते हैं?",
        "chips": [("Kirana / shop", "किराना / दुकान", "kirana store"), ("Salon", "सैलून", "salon"),
                  ("Pharmacy", "दवा की दुकान", "pharmacy"), ("Clinic", "क्लिनिक", "clinic"),
                  ("Restaurant", "रेस्टोरेंट", "restaurant"), ("Office / CA / coaching", "ऑफिस / सीए / कोचिंग", "office"),
                  ("Factory", "फैक्ट्री", "factory")],
    },
    "city": {"en": "Which city is your business in?", "hi": "आपका बिज़नेस किस शहर में है?",
             "chips": [(c, c, c) for c in ("Delhi", "Mumbai", "Bengaluru", "Jaipur", "Lucknow", "Pune")]},
    "employees": {"en": "How many people work there, including you?",
                  "hi": "आपको मिलाकर वहाँ कितने लोग काम करते हैं?",
                  "chips": [(n, n, n) for n in ("1", "2", "3", "5", "10", "20", "50")]},
    "sites": {"en": "How many shops or locations do you have?", "hi": "आपकी कितनी दुकानें या जगहें हैं?",
              "chips": [("1", "1", "1"), ("2", "2", "2"), ("3–5", "3–5", "4"), ("6+", "6+", "6")]},
    "has_gstin": {"en": "Is your business registered for GST (do you have a GSTIN)?",
                  "hi": "क्या आपका बिज़नेस GST में रजिस्टर्ड है (GSTIN है)?",
                  "chips": [("Yes", "हाँ", "yes"), ("No", "नहीं", "no")]},
    "needs": {"en": "What would help your business most? Pick any, or tell me in your words.",
              "hi": "आपके बिज़नेस के लिए क्या सबसे ज़्यादा काम का होगा? चुनें, या अपने शब्दों में बताएँ।",
              "chips": [("UPI billing", "UPI बिलिंग", "billing upi"), ("CCTV", "CCTV", "cctv"),
                        ("Staff SIMs", "स्टाफ़ के सिम", "sim"), ("Customer Wi-Fi", "ग्राहकों का Wi-Fi", "wifi"),
                        ("WhatsApp for customers", "ग्राहकों के लिए WhatsApp", "whatsapp"),
                        ("Business email", "बिज़नेस ईमेल", "email"), ("Antivirus", "एंटीवायरस", "antivirus"),
                        ("Backup internet", "बैकअप इंटरनेट", "backup internet"),
                        ("Only internet", "सिर्फ इंटरनेट", "only internet")]},
}

TEXT = {
    "greeting": {"en": "Namaste! I'm apnaSaathi from Accel Business. I'll ask a few quick questions and suggest "
                       "the right plan with one clear monthly price. You can type or speak, in English or Hindi.",
                 "hi": "नमस्ते! मैं Accel Business का apnaSaathi हूँ। कुछ आसान सवाल पूछकर आपके लिए सही प्लान और एक "
                       "साफ़ मासिक कीमत बताऊँगा। आप हिंदी या इंग्लिश में लिखें या बोलें।"},
    "human": {"en": "Sure. I've asked an Accel expert to call you back, and shared what we've discussed so you "
                    "won't need to repeat it.",
              "hi": "ज़रूर। मैंने Accel के एक्सपर्ट को आपको कॉल करने के लिए कहा है, और अब तक की बात उन्हें भेज दी है "
                    "ताकि आपको दोबारा न बताना पड़े।"},
    "out_of_scope": {"en": "That's not something I can set up here. I can help with business internet, mobile lines, "
                           "billing, CCTV, WhatsApp, email and security.",
                     "hi": "यह मैं यहाँ से सेट नहीं कर सकता। मैं बिज़नेस इंटरनेट, मोबाइल लाइन, बिलिंग, CCTV, "
                           "WhatsApp, ईमेल और सुरक्षा में मदद कर सकता हूँ।"},
    "question_fallback": {"en": "Good question. You'll see full details and the exact price for each item in the quote, "
                                "and an expert can help with anything else.",
                          "hi": "अच्छा सवाल। हर चीज़ की पूरी जानकारी और सही कीमत कोटेशन में दिखेगी, और बाकी में "
                                "एक्सपर्ट मदद करेंगे।"},
    "didnt_get": {"en": "Sorry, I didn't catch that.", "hi": "माफ़ कीजिए, मैं समझ नहीं पाया।"},
    "form": {"en": "Let's make this quicker: please tap your answers below.",
             "hi": "चलिए जल्दी करते हैं: नीचे अपने जवाब चुनें।"},
    "recommend": {"en": "Here's what I recommend for your {business}.", "hi": "आपके {business} के लिए मेरा सुझाव:"},
}


class AdvisorState(BaseModel):
    session_id: str
    language: str = "en"
    channel: str = "web"
    partner_code: Optional[str] = None
    slots: Slots = Slots()
    turns: int = 0
    expecting: Optional[str] = "business_type"
    handoff_requested: bool = False
    llm_failures: int = 0
    completed: bool = False


class AdvisorReply(BaseModel):
    session_id: str
    language: str
    text: str
    expecting: Optional[str] = None
    chips: list[Chip] = []
    show_form: bool = False
    missing: list[str] = []
    slots: Slots
    understood_by: str
    handoff: bool = False
    recommendation: Optional[Recommendation] = None
    summary: Optional[str] = None


def _q(slot: str, lang: str) -> tuple[str, list[Chip]]:
    q = QUESTIONS[slot]
    chips = [Chip(label=(c[1] if lang == "hi" else c[0]), value=c[2]) for c in q["chips"]]
    return q[lang], chips


def greeting(state: AdvisorState) -> AdvisorReply:
    text, chips = _q("business_type", state.language)
    return AdvisorReply(session_id=state.session_id, language=state.language,
                        text=TEXT["greeting"][state.language] + "\n\n" + text, expecting="business_type",
                        chips=chips, missing=state.slots.missing(), slots=state.slots, understood_by="none")


def _understand(text: str, state: AdvisorState, llm: Optional[LLM]) -> tuple[ProfileUpdate, str]:
    rules = nlu_rules.extract(text, state.expecting)
    if llm is None:
        return rules, "rules"
    known = state.slots.model_dump(include={"business_type", "segment", "city", "employees", "sites",
                                            "has_gstin", "needs"})
    try:
        upd = llm.extract(redact(text), state.expecting, known)
    except LLMUnavailable as e:
        state.llm_failures += 1
        log.warning("LLM extract failed (%s); using rules.", e)
        return rules, "rules"
    # Rules fill only what the LLM left empty.
    data = upd.model_dump()
    for k, v in rules.model_dump().items():
        if k == "needs":
            data[k] = list(dict.fromkeys((data.get(k) or []) + v))
        elif k == "no_more_needs":
            data[k] = bool(data.get(k)) or v
        elif k in ("intent", "user_question"):
            continue
        elif data.get(k) is None and v is not None:
            data[k] = v
    if data.get("intent") in (None, "answer", "other") and rules.intent in ("human", "out_of_scope"):
        data["intent"] = rules.intent
    return sanitise(ProfileUpdate(**data)), llm.name


def _catalogue_facts() -> str:
    return "\n".join(f"- {p.product_name} ({p.category}): {p.description}" for p in load_catalogue().values())


def _finish(state: AdvisorState, llm: Optional[LLM], prefix: str, by: str) -> AdvisorReply:
    lang = state.language
    rec = recommend(state.slots, lang)
    state.completed = True
    state.expecting = None
    business = business_label(state.slots.business_type, lang)
    summary = None
    if llm is not None:
        facts = {"business": business, "segment": rec.segment, "city": state.slots.city,
                 "people": state.slots.employees, "locations": state.slots.sites,
                 "recommended": [{"product": l.product_name, "because": l.why} for l in rec.lines],
                 "not_available": [{"product": e.product_name, "reason": e.message} for e in rec.excluded]}
        try:
            summary = safe_text(llm.summarise(facts, lang))
        except LLMUnavailable:
            summary = None
    text = (prefix + " " if prefix else "") + TEXT["recommend"][lang].format(business=business)
    return AdvisorReply(session_id=state.session_id, language=lang, text=text.strip(), slots=state.slots,
                        understood_by=by, recommendation=rec, summary=summary, missing=[])


def handle_message(state: AdvisorState, text: str, llm: Optional[LLM] = None, use_default_llm: bool = True) -> AdvisorReply:
    llm = llm if llm is not None else (get_llm() if use_default_llm else None)
    state.turns += 1
    upd, by = _understand(text, state, llm)
    if upd.language:
        state.language = upd.language
    lang = state.language

    prefix = ""
    if upd.intent == "human":
        state.handoff_requested = True
        state.slots = merge(state.slots, upd)
        return AdvisorReply(session_id=state.session_id, language=lang, text=TEXT["human"][lang],
                            slots=state.slots, understood_by=by, handoff=True, missing=state.slots.missing())
    if upd.intent == "out_of_scope":
        prefix = TEXT["out_of_scope"][lang]
    elif upd.intent == "question" and upd.user_question:
        answer = None
        if llm is not None:
            try:
                answer = safe_text(llm.answer(redact(upd.user_question), _catalogue_facts(), lang))
            except LLMUnavailable:
                answer = None
        prefix = answer or TEXT["question_fallback"][lang]

    # Don't let a generic word ("shop", "office") overwrite a specific business type we already know.
    if state.slots.business_type and upd.business_type in GENERIC_TYPES:
        upd = upd.model_copy(update={"business_type": None, "segment": None})

    before = state.slots.model_dump()
    state.slots = merge(state.slots, upd)
    progressed = state.slots.model_dump() != before

    missing = state.slots.missing()
    if not missing:
        return _finish(state, llm, prefix, by)

    if not progressed and not prefix:
        prefix = TEXT["didnt_get"][lang]
    nxt = missing[0]
    state.expecting = nxt
    question, chips = _q(nxt, lang)
    show_form = state.turns >= MAX_TURNS_BEFORE_FORM or state.llm_failures >= 2
    if show_form:
        prefix = (prefix + " " + TEXT["form"][lang]).strip()
    return AdvisorReply(session_id=state.session_id, language=lang, text=(prefix + "\n\n" + question).strip(),
                        expecting=nxt, chips=chips, show_form=show_form, missing=missing, slots=state.slots,
                        understood_by=by)


def handle_form(state: AdvisorState, slots: Slots) -> AdvisorReply:
    """Fallback path: slots submitted directly from the tap-through form (no LLM involved)."""
    data = state.slots.model_dump()
    for k, v in slots.model_dump().items():
        if k != "needs_confirmed" and v is not None and v != []:
            data[k] = v
    if slots.needs or slots.needs_confirmed:
        data["needs_confirmed"] = True
    if slots.business_type and not slots.segment:
        data["segment"] = None  # re-inferred from the new business type
    state.slots = Slots(**data)
    missing = state.slots.missing()
    if missing:
        state.expecting = missing[0]
        question, chips = _q(missing[0], state.language)
        return AdvisorReply(session_id=state.session_id, language=state.language, text=question,
                            expecting=missing[0], chips=chips, show_form=True, missing=missing,
                            slots=state.slots, understood_by="form")
    return _finish(state, None, "", "form")
