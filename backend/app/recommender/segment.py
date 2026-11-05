"""Business type -> canonical type + segment, from keywords in English, Hindi and Hinglish."""
from __future__ import annotations

import re
from typing import Optional

from app.catalogue.loader import load_reference

# (keywords, canonical business type, segment). Checked in order; first match wins.
BUSINESS_KEYWORDS: list[tuple[tuple[str, ...], str, str]] = [
    # Manufacturers
    (("textile", "कपड़ा मिल", "weaving", "power loom", "powerloom"), "Textile unit", "mfg"),
    (("auto part", "auto-part", "ऑटो पार्ट"), "Auto-parts unit", "mfg"),
    (("plastic", "moulding", "molding", "प्लास्टिक"), "Plastic moulding unit", "mfg"),
    (("packaging", "पैकेजिंग"), "Packaging unit", "mfg"),
    (("food processing", "फूड प्रोसेसिंग"), "Food processing unit", "mfg"),
    (("furniture", "फर्नीचर", "woodcraft"), "Furniture workshop", "mfg"),
    (("printing", "press", "प्रिंटिंग"), "Printing press", "mfg"),
    (("factory", "manufactur", "फैक्ट्री", "कारखाना", "workshop"), "Manufacturing unit", "mfg"),
    # Chains (multi-site when they have several locations)
    (("restaurant chain", "restaurants"), "Restaurant chain", "multi"),
    (("hotel", "होटल", "lodge"), "Budget hotel group", "multi"),
    (("gym", "जिम", "fitness"), "Gym chain", "multi"),
    (("pre-school", "preschool", "play school", "प्ले स्कूल"), "Pre-school chain", "multi"),
    # Professional offices
    (("dental", "dentist", "डेंटल", "दांत"), "Dental clinic", "prof"),
    (("diagnostic", "pathology", "path lab", "लैब", "पैथोलॉजी"), "Diagnostic lab", "prof"),
    (("physio", "फिजियो"), "Physiotherapy clinic", "prof"),
    (("real estate", "property", "प्रॉपर्टी", "रियल एस्टेट"), "Real estate agency", "prof"),
    (("law ", "lawyer", "advocate", "legal", "वकील"), "Law office", "prof"),
    (("coaching", "tuition", "कोचिंग", "ट्यूशन"), "Coaching centre", "prof"),
    (("ca firm", "chartered accountant", "accountant", "सीए", "ca office"), "CA firm", "prof"),
    (("architect", "आर्किटेक्ट"), "Architecture studio", "prof"),
    (("travel", "ट्रैवल", "tour"), "Travel agency", "prof"),
    (("insurance", "बीमा", "इंश्योरेंस"), "Insurance agency", "prof"),
    (("clinic", "क्लिनिक", "doctor", "डॉक्टर", "hospital", "अस्पताल"), "Clinic", "prof"),
    (("office", "ऑफिस", "दफ्तर", "consult"), "Office", "prof"),
    # Micro retail and services
    (("mobile repair", "phone repair", "मोबाइल रिपेयर", "mobile shop", "मोबाइल की दुकान"), "Mobile repair shop", "micro"),
    (("kirana", "किराना", "grocery", "general store", "परचून", "provision"), "Kirana store", "micro"),
    (("salon", "parlour", "parlor", "सैलून", "पार्लर", "barber", "नाई"), "Salon", "micro"),
    (("pharmacy", "chemist", "medical store", "medical shop", "दवा", "केमिस्ट", "मेडिकल"), "Pharmacy", "micro"),
    (("bakery", "बेकरी", "bake"), "Bakery", "micro"),
    (("stationery", "स्टेशनरी"), "Stationery shop", "micro"),
    (("optician", "optical", "चश्मा", "ऑप्टिकल"), "Optician", "micro"),
    (("hardware", "हार्डवेयर"), "Hardware store", "micro"),
    (("boutique", "बुटीक", "clothes", "कपड़े", "garment"), "Boutique", "micro"),
    (("sweet", "mithai", "मिठाई", "हलवाई"), "Sweet shop", "micro"),
    (("restaurant", "रेस्टोरेंट", "dhaba", "ढाबा", "cafe", "कैफे", "eatery"), "Restaurant", "micro"),
    (("shop", "store", "दुकान"), "Retail shop", "micro"),
]


def match_business_type(text: str) -> Optional[tuple[str, str]]:
    """Return (canonical_type, segment) if the text names a known kind of business."""
    t = " " + text.lower() + " "
    for name, seg in load_reference()["business_types"].items():
        if re.search(r"\b" + re.escape(name.lower()) + r"\b", t):
            return name, seg
    for keywords, canonical, seg in BUSINESS_KEYWORDS:
        if any(k in t for k in keywords):
            return canonical, seg
    return None


def infer_segment(business_type: Optional[str], sites: Optional[int], hint: Optional[str] = None) -> str:
    """Segment from business type and number of locations.

    - Manufacturing stays 'mfg'.
    - 3 or more locations -> 'multi' (case: "3-10 store retailer").
    - A chain-type business with a single location is treated as micro retail.
    """
    seg = None
    if business_type:
        m = match_business_type(business_type)
        seg = m[1] if m else None
    seg = seg or hint or "micro"
    if seg == "mfg":
        return seg
    if sites and sites >= 3:
        return "multi"
    if seg == "multi" and (sites or 1) < 2:
        return "micro"
    return seg
