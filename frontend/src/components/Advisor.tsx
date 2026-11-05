import { useEffect, useRef, useState } from "react";
import { Check, FileCheck, FileX, Minus, Mic, Plus, SendHorizontal, Store, Users, Volume2 } from "lucide-react";
import type { AdvisorReply, Lang, Slots } from "../api";
import { inr } from "../api";
import { cityName, countLabel, t } from "../i18n";
import { speak, speechSupported, useListen } from "../speech";
import { Icon } from "./Icon";

export interface ChatMsg { role: "a" | "u"; text: string; summary?: string | null }

type Tile = { icon: string; en: string; hi: string; value: string };

const BUSINESS: Tile[] = [
  { icon: "store", en: "Kirana / general store", hi: "किराना / जनरल स्टोर", value: "Kirana store" },
  { icon: "scissors", en: "Salon / parlour", hi: "सैलून / पार्लर", value: "Salon" },
  { icon: "pill", en: "Pharmacy", hi: "दवा की दुकान", value: "Pharmacy" },
  { icon: "stethoscope", en: "Clinic / lab", hi: "क्लिनिक / लैब", value: "Clinic" },
  { icon: "utensils", en: "Restaurant / café", hi: "रेस्टोरेंट / ढाबा", value: "Restaurant" },
  { icon: "briefcase", en: "Office: CA, coaching, agency", hi: "ऑफ़िस: सीए, कोचिंग, एजेंसी", value: "Office" },
  { icon: "factory", en: "Factory / workshop", hi: "फ़ैक्ट्री / वर्कशॉप", value: "Manufacturing unit" },
  { icon: "building", en: "Shop with many branches", hi: "कई ब्रांच वाली दुकान", value: "Retail shop" },
];

const NEEDS: (Tile & { segs: string[] })[] = [
  { icon: "qr-code", en: "UPI billing", hi: "UPI बिलिंग", value: "billing_upi", segs: ["micro", "multi"] },
  { icon: "cctv", en: "CCTV camera", hi: "CCTV कैमरा", value: "cctv", segs: ["micro", "multi", "mfg"] },
  { icon: "smartphone", en: "SIMs for staff", hi: "स्टाफ़ के सिम", value: "mobile_lines", segs: ["micro", "prof", "multi", "mfg"] },
  { icon: "wifi", en: "Wi-Fi for customers", hi: "ग्राहकों का Wi-Fi", value: "guest_wifi", segs: ["micro", "multi"] },
  { icon: "message-circle", en: "WhatsApp for customers", hi: "ग्राहकों के लिए WhatsApp", value: "whatsapp_customers", segs: ["micro", "prof", "multi"] },
  { icon: "mail", en: "Business email", hi: "बिज़नेस ईमेल", value: "email_office", segs: ["prof", "multi", "mfg"] },
  { icon: "shield-check", en: "Antivirus", hi: "एंटीवायरस", value: "security", segs: ["prof", "mfg", "multi"] },
  { icon: "life-buoy", en: "Backup internet", hi: "बैकअप इंटरनेट", value: "uptime_backup", segs: ["prof", "multi", "mfg"] },
  { icon: "globe", en: "Website", hi: "वेबसाइट", value: "website", segs: ["micro", "prof"] },
  { icon: "hard-drive", en: "Data backup", hi: "डेटा बैकअप", value: "backup_files", segs: ["prof"] },
  { icon: "truck", en: "Vehicle GPS", hi: "गाड़ी की GPS", value: "vehicles", segs: ["multi", "mfg"] },
  { icon: "activity", en: "Machine monitoring", hi: "मशीन की निगरानी", value: "machines_iot", segs: ["mfg"] },
];

const CITIES: [string, string][] = [
  ["Delhi", "दिल्ली"], ["Mumbai", "मुंबई"], ["Bengaluru", "बेंगलुरु"], ["Hyderabad", "हैदराबाद"],
  ["Jaipur", "जयपुर"], ["Lucknow", "लखनऊ"], ["Pune", "पुणे"], ["Indore", "इंदौर"], ["Patna", "पटना"], ["Surat", "सूरत"],
];

const SLOT_LABEL: Record<string, (v: unknown, lang: Lang) => string> = {
  business_type: (v, l) => (l === "hi" ? BUSINESS.find((b) => b.value === v)?.hi.split(" / ")[0] ?? String(v) : String(v)),
  city: (v, l) => cityName(String(v), l),
  employees: (v, l) => countLabel("people", Number(v), l),
  sites: (v, l) => countLabel("sites", Number(v), l),
  has_gstin: (v, l) => (v ? (l === "hi" ? "GST है" : "has GST") : (l === "hi" ? "GST नहीं" : "no GST")),
};

function Known({ slots, lang }: { slots: Slots; lang: Lang }) {
  const items = (Object.keys(SLOT_LABEL) as (keyof Slots)[])
    .filter((k) => slots[k] !== null && slots[k] !== undefined)
    .map((k) => SLOT_LABEL[k](slots[k], lang));
  if (!items.length) return null;
  return (
    <div className="known" aria-live="polite">
      <Check size={16} aria-hidden="true" />{t(lang, "understood")}
      {items.map((i) => <span className="k" key={i}>{i}</span>)}
    </div>
  );
}

function Stepper({ value, setValue, label, icon, min = 1, max = 500 }:
  { value: number; setValue: (n: number) => void; label: string; icon: React.ReactNode; min?: number; max?: number }) {
  return (
    <div className="stepper">
      <span className="lbl">{icon}{label}</span>
      <button className="round" aria-label="−" disabled={value <= min} onClick={() => setValue(Math.max(min, value - 1))}><Minus /></button>
      <span className="val" aria-live="polite">{value}</span>
      <button className="round" aria-label="+" disabled={value >= max} onClick={() => setValue(Math.min(max, value + 1))}><Plus /></button>
    </div>
  );
}

function AnswerPanel({ reply, lang, busy, onForm, onText }:
  { reply: AdvisorReply; lang: Lang; busy: boolean; onForm: (s: Slots, label: string) => void; onText: (s: string) => void }) {
  const exp = reply.expecting;
  const [num, setNum] = useState(exp === "sites" ? 1 : 3);
  const [picked, setPicked] = useState<string[]>([]);
  const [showAll, setShowAll] = useState(false);
  useEffect(() => { setNum(exp === "sites" ? 1 : 3); setPicked([]); setShowAll(false); }, [exp]);
  if (!exp) return null;
  const L = (x: { en: string; hi: string }) => (lang === "hi" ? x.hi : x.en);

  if (exp === "business_type") {
    return (
      <div className="answer">
        <div className="tiles">
          {BUSINESS.map((b) => (
            <button key={b.value} className="tile" disabled={busy} onClick={() => onForm({ business_type: b.value }, L(b))}>
              <span className="ic"><Icon name={b.icon} /></span>{L(b)}
            </button>
          ))}
        </div>
        <p className="hint">{t(lang, "otherBusiness")}</p>
      </div>
    );
  }
  if (exp === "city") {
    return (
      <div className="answer">
        <div className="chips">
          {CITIES.map(([en, hi]) => (
            <button key={en} className="chip" disabled={busy} onClick={() => onForm({ city: en }, lang === "hi" ? hi : en)}>
              {lang === "hi" ? hi : en}
            </button>
          ))}
        </div>
        <p className="hint">{t(lang, "cityHint")}</p>
      </div>
    );
  }
  if (exp === "employees" || exp === "sites") {
    const isEmp = exp === "employees";
    return (
      <div className="answer">
        <Stepper value={num} setValue={setNum} label={t(lang, isEmp ? "people" : "locations")}
                 icon={isEmp ? <Users size={20} /> : <Store size={20} />} max={isEmp ? 500 : 50} />
        <div className="row-actions">
          <button className="btn btn-primary" disabled={busy}
                  onClick={() => onForm(isEmp ? { employees: num } : { sites: num },
                    countLabel(isEmp ? "people" : "sites", num, lang))}>{t(lang, "next")}</button>
        </div>
      </div>
    );
  }
  if (exp === "has_gstin") {
    return (
      <div className="answer">
        <div className="yesno">
          <button className="tile" disabled={busy} onClick={() => onForm({ has_gstin: true }, t(lang, "yes"))}>
            <span className="ic"><FileCheck /></span>{t(lang, "yes")}
          </button>
          <button className="tile" disabled={busy} onClick={() => onForm({ has_gstin: false }, t(lang, "no"))}>
            <span className="ic"><FileX /></span>{t(lang, "no")}
          </button>
        </div>
        <p className="hint">{t(lang, "gstHelp")}</p>
      </div>
    );
  }
  if (exp === "needs") {
    const seg = reply.slots.segment || "micro";
    const relevant = NEEDS.filter((n) => n.segs.includes(seg));
    const list = showAll ? NEEDS : relevant;
    const toggle = (v: string) => setPicked((p) => (p.includes(v) ? p.filter((x) => x !== v) : [...p, v]));
    const labels = NEEDS.filter((n) => picked.includes(n.value)).map(L).join(", ");
    return (
      <div className="answer">
        <p className="hint" style={{ marginTop: 0, marginBottom: 10 }}>{t(lang, "pickAny")}</p>
        <div className="tiles">
          {list.map((n) => (
            <button key={n.value} className="tile" aria-pressed={picked.includes(n.value)} onClick={() => toggle(n.value)}>
              <span className="ic"><Icon name={n.icon} /></span>{L(n)}
            </button>
          ))}
        </div>
        {!showAll && relevant.length < NEEDS.length && (
          <button className="linkbtn" onClick={() => setShowAll(true)}>{lang === "hi" ? "और विकल्प" : "More options"}</button>
        )}
        <div className="row-actions">
          <button className="btn btn-primary" disabled={busy || picked.length === 0}
                  onClick={() => onForm({ needs: picked }, labels)}>
            {t(lang, "needsDone")}{picked.length ? ` (${picked.length})` : ""}
          </button>
          <button className="btn btn-secondary" disabled={busy}
                  onClick={() => onForm({ needs: ["internet"] }, t(lang, "onlyInternet"))}>{t(lang, "onlyInternet")}</button>
        </div>
      </div>
    );
  }
  return (
    <div className="answer">
      <div className="chips">
        {reply.chips.map((c) => <button key={c.value} className="chip" disabled={busy} onClick={() => onText(c.value)}>{c.label}</button>)}
      </div>
    </div>
  );
}

export function Advisor({ lang, msgs, reply, busy, autoListen, quoteTotal, onText, onForm, onViewQuote }: {
  lang: Lang; msgs: ChatMsg[]; reply: AdvisorReply | null; busy: boolean; autoListen: boolean;
  quoteTotal: number | null; onText: (s: string) => void; onForm: (s: Slots, label: string) => void; onViewQuote: () => void;
}) {
  const [text, setText] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const { listening, interim, start, stop } = useListen(lang, (s) => onText(s));
  const startedRef = useRef(false);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs.length, busy, reply?.expecting]);
  useEffect(() => {
    if (autoListen && !startedRef.current && reply && !busy) { startedRef.current = true; start(); }
  }, [autoListen, reply, busy, start]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (text.trim()) { onText(text.trim()); setText(""); }
  };

  return (
    <section className="chat" aria-label="apnaSaathi">
      <div className="thread" role="log" aria-live="polite">
        {msgs.length === 0 && <p className="typing">{t(lang, "emptyChat")}</p>}
        {msgs.map((m, i) =>
          m.role === "a" ? (
            <div key={i}>
              <div className="msg-a">
                <button className="say" aria-label={t(lang, "speakReply")} onClick={() => speak(m.text, lang)}><Volume2 size={20} /></button>
                <span>{m.text}</span>
              </div>
              {m.summary && <p className="summary">{m.summary}</p>}
            </div>
          ) : <div key={i} className="msg-u">{m.text}</div>
        )}
        {busy && <p className="typing">…</p>}
        {reply && <Known slots={reply.slots} lang={lang} />}
      </div>
      {reply && !reply.recommendation && !reply.handoff &&
        <AnswerPanel reply={reply} lang={lang} busy={busy} onForm={onForm} onText={onText} />}
      <div ref={endRef} style={{ scrollMarginBottom: 150 }} aria-hidden="true" />
      <div className="composer">
        {quoteTotal !== null && (
          <div className="planbar">
            <div><small>{t(lang, "sofar")}</small><b>{inr(quoteTotal)}</b>{t(lang, "perMonth")}</div>
            <button className="btn btn-primary" onClick={onViewQuote}>{t(lang, "viewQuote")}</button>
          </div>
        )}
        <form className="inner" onSubmit={submit}>
          <label className="sr-only" htmlFor="say">{t(lang, "typeOrSpeak")}</label>
          <input id="say" value={listening ? interim : text} onChange={(e) => setText(e.target.value)}
                 placeholder={listening ? t(lang, "listening") : t(lang, "typeOrSpeak")} autoComplete="off" disabled={busy} />
          {text.trim() ? (
            <button className="send" type="submit" aria-label={t(lang, "send")} disabled={busy}><SendHorizontal /></button>
          ) : speechSupported() ? (
            <button type="button" className={`mic ${listening ? "on" : ""}`} aria-pressed={listening}
                    aria-label={listening ? t(lang, "listening") : t(lang, "typeOrSpeak")} onClick={() => (listening ? stop() : start())} disabled={busy}>
              <Mic size={28} />
            </button>
          ) : null}
        </form>
      </div>
    </section>
  );
}
