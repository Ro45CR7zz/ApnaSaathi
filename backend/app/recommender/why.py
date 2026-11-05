"""Plain-language reasons for each recommended line (EN/HI). Deterministic templates."""
from __future__ import annotations

WHY: dict[str, dict[str, str]] = {
    "base_fibre": {"en": "Reliable business fibre for {sites_text}: the foundation everything else runs on.",
                   "hi": "{sites_text_hi} के लिए भरोसेमंद बिज़नेस फ़ाइबर: बाकी सब इसी पर चलता है।"},
    "base_airfiber": {"en": "Wireless 5G broadband, plug-and-play, because fibre isn't available at your place.",
                      "hi": "वायरलेस 5G ब्रॉडबैंड, लगाते ही चालू, क्योंकि आपकी जगह पर फ़ाइबर उपलब्ध नहीं है।"},
    "base_leased": {"en": "A dedicated leased line with an uptime guarantee, sized for {employees} people.",
                    "hi": "{employees} लोगों के लिए अपटाइम गारंटी वाली समर्पित लीज़्ड लाइन।"},
    "base_fast": {"en": "Faster fibre because {employees} people share the connection.",
                  "hi": "तेज़ फ़ाइबर, क्योंकि {employees} लोग कनेक्शन इस्तेमाल करते हैं।"},
    "mobile_lines": {"en": "{qty} business mobile line(s) on one bill.",
                     "hi": "एक ही बिल पर {qty} बिज़नेस मोबाइल लाइन।"},
    "billing_upi": {"en": "You mentioned billing / UPI payments: billing with UPI and card acceptance, plus stock records.",
                    "hi": "आपने बिलिंग / UPI पेमेंट की बात की: UPI और कार्ड से बिलिंग, साथ में स्टॉक का हिसाब।"},
    "cctv": {"en": "You asked for CCTV: {qty} HD camera(s) with 30-day cloud recording, viewable on your phone.",
             "hi": "आपने CCTV माँगा: {qty} HD कैमरे, 30 दिन की क्लाउड रिकॉर्डिंग, फ़ोन पर देख सकते हैं।"},
    "guest_wifi": {"en": "Separate Wi-Fi for customers, so your own network stays safe.",
                   "hi": "ग्राहकों के लिए अलग Wi-Fi, ताकि आपका अपना नेटवर्क सुरक्षित रहे।"},
    "whatsapp_customers": {"en": "A verified WhatsApp Business channel with a catalogue for your customers.",
                           "hi": "ग्राहकों के लिए कैटलॉग के साथ वेरिफ़ाइड WhatsApp Business चैनल।"},
    "sms_alerts": {"en": "Bulk SMS for alerts and offers to customers.",
                   "hi": "ग्राहकों को अलर्ट और ऑफ़र भेजने के लिए बल्क SMS।"},
    "website": {"en": "Your own domain and a simple website so customers can find you online.",
                "hi": "अपना डोमेन और आसान वेबसाइट, ताकि ग्राहक आपको ऑनलाइन ढूँढ सकें।"},
    "email_office": {"en": "Business email on your own domain plus documents and video meetings for {qty} user(s).",
                     "hi": "{qty} लोगों के लिए अपने डोमेन पर बिज़नेस ईमेल, डॉक्यूमेंट और वीडियो मीटिंग।"},
    "backup_files": {"en": "Automatic backup of your PCs and phones so data isn't lost.",
                     "hi": "PC और फ़ोन का ऑटोमैटिक बैकअप, ताकि डेटा न खोए।"},
    "security_endpoint": {"en": "Antivirus and ransomware protection for {qty} device(s).",
                          "hi": "{qty} डिवाइस के लिए एंटीवायरस और रैनसमवेयर सुरक्षा।"},
    "security_firewall": {"en": "A managed firewall at your site, run by Accel's security team.",
                          "hi": "आपकी जगह पर मैनेज्ड फ़ायरवॉल, जिसे Accel की सुरक्षा टीम चलाती है।"},
    "uptime_backup": {"en": "Automatic backup internet when the main line goes down.",
                      "hi": "मेन लाइन बंद होने पर अपने-आप चालू होने वाला बैकअप इंटरनेट।"},
    "central_management": {"en": "Manage all {sites} locations' internet from one place.",
                           "hi": "सभी {sites} जगहों का इंटरनेट एक जगह से संभालें।"},
    "static_ip": {"en": "A fixed public IP for CCTV, servers or remote access.",
                  "hi": "CCTV, सर्वर या रिमोट एक्सेस के लिए फ़िक्स्ड पब्लिक IP।"},
    "cloud_calling": {"en": "Business phone lines over the internet with IVR and call recording.",
                      "hi": "IVR और कॉल रिकॉर्डिंग के साथ इंटरनेट पर बिज़नेस फ़ोन लाइनें।"},
    "toll_free": {"en": "A 1800 toll-free number for your customers.",
                  "hi": "ग्राहकों के लिए 1800 टोल-फ़्री नंबर।"},
    "machines_iot": {"en": "Sensors to track machine uptime and energy use ({qty} device(s)).",
                     "hi": "मशीनों का अपटाइम और बिजली खपत देखने के लिए सेंसर ({qty} डिवाइस)।"},
    "vehicles": {"en": "GPS tracking for {qty} vehicle(s) with a live dashboard.",
                 "hi": "{qty} गाड़ियों के लिए लाइव डैशबोर्ड के साथ GPS ट्रैकिंग।"},
}


def why(code: str, lang: str, **params) -> str:
    sites = params.get("sites", 1)
    params.setdefault("sites_text", "your shop" if sites == 1 else f"each of your {sites} locations")
    params.setdefault("sites_text_hi", "आपकी दुकान" if sites == 1 else f"आपकी सभी {sites} जगहों")
    t = WHY[code].get(lang) or WHY[code]["en"]
    return t.format(**params)
