"""How products and business types are shown to owners: an icon plus everyday words (EN/HI).

Product names stay as in the catalogue; these labels explain them in plain language.
Icons are Lucide icon names (open-source, used by the frontend).
"""
from __future__ import annotations

PRODUCTS: dict[str, dict[str, str]] = {
    "P01": {"icon": "router", "en": "Wired internet for your shop", "hi": "दुकान के लिए तार वाला इंटरनेट"},
    "P02": {"icon": "router", "en": "Faster wired internet", "hi": "तेज़ तार वाला इंटरनेट"},
    "P03": {"icon": "router", "en": "Very fast wired internet", "hi": "बहुत तेज़ तार वाला इंटरनेट"},
    "P04": {"icon": "radio-tower", "en": "Wireless 5G internet", "hi": "बिना तार वाला 5G इंटरनेट"},
    "P05": {"icon": "cable", "en": "Dedicated internet line", "hi": "सिर्फ़ आपके लिए इंटरनेट लाइन"},
    "P06": {"icon": "cable", "en": "Dedicated high-speed line", "hi": "सिर्फ़ आपके लिए तेज़ इंटरनेट लाइन"},
    "P07": {"icon": "smartphone", "en": "Business mobile SIM", "hi": "बिज़नेस मोबाइल सिम"},
    "P08": {"icon": "smartphone", "en": "Business mobile SIM with more data", "hi": "ज़्यादा डेटा वाला बिज़नेस सिम"},
    "P09": {"icon": "life-buoy", "en": "Backup internet when the line is down", "hi": "लाइन बंद होने पर बैकअप इंटरनेट"},
    "P10": {"icon": "network", "en": "Manage all locations' internet together", "hi": "सब जगहों का इंटरनेट एक साथ संभालें"},
    "P11": {"icon": "pin", "en": "Fixed internet address", "hi": "फ़िक्स्ड इंटरनेट एड्रेस"},
    "P12": {"icon": "phone-call", "en": "Office phone lines over internet", "hi": "इंटरनेट से ऑफ़िस फ़ोन लाइन"},
    "P13": {"icon": "phone", "en": "1800 toll-free number", "hi": "1800 टोल-फ़्री नंबर"},
    "P14": {"icon": "message-square-text", "en": "Bulk SMS to customers", "hi": "ग्राहकों को बल्क SMS"},
    "P15": {"icon": "message-circle", "en": "WhatsApp for your customers", "hi": "ग्राहकों के लिए WhatsApp"},
    "P16": {"icon": "mail", "en": "Business email", "hi": "बिज़नेस ईमेल"},
    "P17": {"icon": "hard-drive", "en": "Data backup", "hi": "डेटा बैकअप"},
    "P18": {"icon": "globe", "en": "Your own website", "hi": "आपकी अपनी वेबसाइट"},
    "P19": {"icon": "qr-code", "en": "Billing with UPI and card", "hi": "UPI और कार्ड से बिलिंग"},
    "P20": {"icon": "shield-check", "en": "Antivirus for devices", "hi": "डिवाइस के लिए एंटीवायरस"},
    "P21": {"icon": "shield", "en": "Firewall for your office", "hi": "ऑफ़िस के लिए फ़ायरवॉल"},
    "P22": {"icon": "wifi", "en": "Wi-Fi for customers", "hi": "ग्राहकों के लिए Wi-Fi"},
    "P23": {"icon": "cctv", "en": "CCTV camera", "hi": "CCTV कैमरा"},
    "P24": {"icon": "activity", "en": "Machine monitoring", "hi": "मशीन की निगरानी"},
    "P25": {"icon": "truck", "en": "Vehicle GPS tracking", "hi": "गाड़ी की GPS ट्रैकिंग"},
}

UNIT_WORDS = {
    "per site": ("location", "जगह"), "per line": ("SIM", "सिम"), "per IP": ("address", "एड्रेस"),
    "per channel": ("line", "लाइन"), "per number": ("number", "नंबर"), "per pack": ("pack", "पैक"),
    "per account": ("account", "अकाउंट"), "per user": ("person", "व्यक्ति"), "per counter": ("counter", "काउंटर"),
    "per device": ("device", "डिवाइस"), "per camera": ("camera", "कैमरा"), "per vehicle": ("vehicle", "गाड़ी"),
}

BUSINESS_TYPES_HI = {
    "Kirana store": "किराना दुकान", "Salon": "सैलून", "Pharmacy": "दवा की दुकान", "Bakery": "बेकरी",
    "Stationery shop": "स्टेशनरी दुकान", "Optician": "चश्मे की दुकान", "Hardware store": "हार्डवेयर दुकान",
    "Boutique": "बुटीक", "Sweet shop": "मिठाई की दुकान", "Mobile repair shop": "मोबाइल रिपेयर दुकान",
    "Restaurant": "रेस्टोरेंट", "Retail shop": "दुकान", "Dental clinic": "डेंटल क्लिनिक",
    "Diagnostic lab": "जाँच लैब", "Physiotherapy clinic": "फिज़ियोथेरेपी क्लिनिक",
    "Real estate agency": "प्रॉपर्टी एजेंसी", "Law office": "वकील का ऑफ़िस", "Coaching centre": "कोचिंग सेंटर",
    "CA firm": "सीए ऑफ़िस", "Architecture studio": "आर्किटेक्ट ऑफ़िस", "Travel agency": "ट्रैवल एजेंसी",
    "Insurance agency": "बीमा एजेंसी", "Clinic": "क्लिनिक", "Office": "ऑफ़िस",
    "Electronics retail chain": "इलेक्ट्रॉनिक्स दुकानें", "Apparel retail chain": "कपड़ों की दुकानें",
    "Bakery chain": "बेकरी की दुकानें", "Restaurant chain": "रेस्टोरेंट", "Pharmacy chain": "दवा की दुकानें",
    "Pre-school chain": "प्ले स्कूल", "Budget hotel group": "होटल", "Gym chain": "जिम",
    "Auto-parts unit": "ऑटो पार्ट्स यूनिट", "Textile unit": "कपड़ा यूनिट", "Plastic moulding unit": "प्लास्टिक यूनिट",
    "Packaging unit": "पैकेजिंग यूनिट", "Food processing unit": "फ़ूड प्रोसेसिंग यूनिट",
    "Furniture workshop": "फ़र्नीचर वर्कशॉप", "Printing press": "प्रिंटिंग प्रेस", "Manufacturing unit": "फ़ैक्ट्री",
}


def product_display(product_id: str, lang: str) -> dict[str, str]:
    d = PRODUCTS.get(product_id, {"icon": "package", "en": "", "hi": ""})
    return {"icon": d["icon"], "plain": d.get(lang) or d["en"]}


def unit_word(unit: str, lang: str) -> str:
    en, hi = UNIT_WORDS.get(unit, ("unit", "यूनिट"))
    return hi if lang == "hi" else en


def business_label(business_type: str | None, lang: str) -> str:
    if not business_type:
        return "बिज़नेस" if lang == "hi" else "business"
    return BUSINESS_TYPES_HI.get(business_type, business_type) if lang == "hi" else business_type


def inr(amount: int) -> str:
    """Indian digit grouping: 123100 -> '1,23,100'."""
    sign, n = ("-" if amount < 0 else ""), str(abs(int(amount)))
    if len(n) <= 3:
        return sign + n
    head, tail = n[:-3], n[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return sign + ",".join(groups + [tail])
