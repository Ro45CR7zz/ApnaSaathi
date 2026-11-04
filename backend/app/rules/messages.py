"""Plain-language explanations for every rule outcome, in English and Hindi."""
from __future__ import annotations

MESSAGES: dict[str, dict[str, str]] = {
    "TIER_UNAVAILABLE": {
        "en": "{product} is not available in your city yet.",
        "hi": "{product} अभी आपके शहर में उपलब्ध नहीं है।",
    },
    "BELOW_MIN_EMPLOYEES": {
        "en": "{product} is for businesses with at least {min_employees} employees (you have {employees}).",
        "hi": "{product} कम से कम {min_employees} कर्मचारियों वाले व्यवसायों के लिए है (आपके पास {employees} हैं)।",
    },
    "BELOW_MIN_SITES": {
        "en": "{product} is for businesses with at least {min_sites} locations (you have {sites}).",
        "hi": "{product} कम से कम {min_sites} जगहों वाले व्यवसायों के लिए है (आपकी {sites} जगहें हैं)।",
    },
    "GSTIN_REQUIRED": {
        "en": "{product} needs a GST registration (GSTIN). You can add it later once you have one.",
        "hi": "{product} के लिए GST रजिस्ट्रेशन (GSTIN) ज़रूरी है। GSTIN मिलने पर आप इसे बाद में जोड़ सकते हैं।",
    },
    "GSTIN_INACTIVE": {
        "en": "{product} needs an active GSTIN, and the GSTIN on record is {status}.",
        "hi": "{product} के लिए सक्रिय GSTIN ज़रूरी है, लेकिन रिकॉर्ड में आपका GSTIN {status} है।",
    },
    "DEPENDENCY_MISSING": {
        "en": "{product} works only together with one of: {options}.",
        "hi": "{product} केवल इनमें से किसी एक के साथ काम करता है: {options}।",
    },
    "DEPENDENCY_AUTO_ADDED": {
        "en": "We added {added} because {product} needs it to work.",
        "hi": "हमने {added} जोड़ा है क्योंकि {product} को काम करने के लिए इसकी ज़रूरत है।",
    },
    "UNKNOWN_PRODUCT": {
        "en": "Product {product_id} is not in the catalogue.",
        "hi": "प्रोडक्ट {product_id} कैटलॉग में नहीं है।",
    },
    "DUPLICATE_PRODUCT": {
        "en": "{product} appears more than once; please combine the quantities.",
        "hi": "{product} एक से ज़्यादा बार है; कृपया मात्रा को एक साथ जोड़ें।",
    },
    "QTY_EXCEEDS_SITES": {
        "en": "{product} is per location; {qty} is more than your {sites} locations.",
        "hi": "{product} हर जगह के हिसाब से है; {qty} आपकी {sites} जगहों से ज़्यादा है।",
    },
    "UNVERIFIED_CITY": {
        "en": "We couldn't confirm availability in {city}, so we used the more limited tier-2 list. Availability will be confirmed.",
        "hi": "{city} में उपलब्धता की पुष्टि नहीं हो सकी, इसलिए हमने सीमित (टियर-2) सूची ली है। उपलब्धता की पुष्टि की जाएगी।",
    },
}

STATUS_HI = {"Cancelled": "रद्द", "Suspended": "निलंबित", "NotFound": "नहीं मिला"}


def render(code: str, lang: str = "en", **params) -> str:
    template = MESSAGES[code].get(lang) or MESSAGES[code]["en"]
    if lang == "hi" and "status" in params:
        params = {**params, "status": STATUS_HI.get(params["status"], params["status"])}
    return template.format(**params)
