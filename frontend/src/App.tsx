import { useCallback, useEffect, useState } from "react";
import { api, type AdvisorReply, type Lang, type Order, type Quote, type QuoteChange, type Slots } from "./api";
import { Advisor, type ChatMsg } from "./components/Advisor";
import { Bill } from "./components/Bill";
import { Checkout, Done } from "./components/Checkout";
import { Header, Journey } from "./components/Header";
import { Kyc } from "./components/Kyc";
import { Welcome } from "./components/Welcome";
import { t } from "./i18n";

type Screen = "welcome" | "advisor" | "quote" | "checkout" | "done" | "kyc";

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem("apnasaathi.lang");
    if (saved === "en" || saved === "hi") return saved;
  } catch { /* storage unavailable */ }
  return "hi"; // Hindi first: most owners in the data prefer an Indian language
}

const wide = () => typeof window !== "undefined" && window.matchMedia("(min-width: 960px)").matches;

export default function App() {
  const [lang, setLangState] = useState<Lang>(initialLang);
  const [screen, setScreen] = useState<Screen>("welcome");
  const [sid, setSid] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [reply, setReply] = useState<AdvisorReply | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [busy, setBusy] = useState(false);
  const [autoListen, setAutoListen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [checkoutErr, setCheckoutErr] = useState<string | null>(null);
  const [isWide, setIsWide] = useState(wide());
  const [kycOutcome, setKycOutcome] = useState<string | null>(null);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 960px)");
    const on = () => setIsWide(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  useEffect(() => { if (screen !== "advisor") window.scrollTo({ top: 0 }); }, [screen]);
  useEffect(() => { if (toast) { const id = setTimeout(() => setToast(null), 3500); return () => clearTimeout(id); } }, [toast]);

  const fail = () => setToast(t(lang, "error"));

  const setLang = async (l: Lang) => {
    setLangState(l);
    try { localStorage.setItem("apnasaathi.lang", l); } catch { /* ignore */ }
    if (quote && quote.status === "open") {
      try { setQuote(await api.changeQuote(quote.id, { language: l })); } catch { fail(); }
    }
  };

  const handleReply = useCallback(async (r: AdvisorReply) => {
    setReply(r);
    setMsgs((m) => [...m, { role: "a", text: r.text, summary: r.summary }]);
    if (r.handoff) setToast(t(r.language, "callRequested"));
    if (r.recommendation) {
      const q = await api.createQuote(r.session_id, r.language);
      setQuote(q);
      if (!wide()) setScreen("quote");
    }
  }, []);

  const start = async (voice: boolean) => {
    setScreen("advisor");
    setAutoListen(voice);
    setBusy(true);
    try {
      const r = await api.start(lang);
      setSid(r.session_id);
      setReply(r);
      setMsgs([{ role: "a", text: r.text }]);
    } catch { fail(); } finally { setBusy(false); }
  };

  const sendText = async (text: string) => {
    if (!sid) return;
    setMsgs((m) => [...m, { role: "u", text }]);
    setBusy(true);
    try { await handleReply(await api.message(sid, text, lang)); } catch { fail(); } finally { setBusy(false); }
  };

  const sendForm = async (slots: Slots, label: string) => {
    if (!sid) return;
    setMsgs((m) => [...m, { role: "u", text: label }]);
    setBusy(true);
    try { await handleReply(await api.form(sid, slots, lang)); } catch { fail(); } finally { setBusy(false); }
  };

  const callMe = async () => {
    try {
      let id = sid;
      if (!id) { const r = await api.start(lang); id = r.session_id; setSid(id); }
      await api.message(id, "talk to a person", lang);
      setToast(t(lang, "callRequested"));
    } catch { fail(); }
  };

  const change = async (c: QuoteChange) => {
    if (!quote) return;
    setBusy(true);
    try { setQuote(await api.changeQuote(quote.id, c)); } catch { fail(); } finally { setBusy(false); }
  };

  const share = async () => {
    if (!quote) return;
    try {
      const { text } = await api.share(quote.id, lang);
      if (navigator.share) { await navigator.share({ text }).catch(() => undefined); }
      else window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener");
    } catch { fail(); }
  };

  const accept = async (name: string, mobile: string, consent: boolean) => {
    if (!quote) return;
    setBusy(true);
    setCheckoutErr(null);
    try {
      const o = await api.accept(quote.id, name, mobile, consent);
      setOrder(o);
      setQuote({ ...quote, status: "accepted", order_id: o.id });
      setScreen("done");
    } catch (e) {
      setCheckoutErr(e instanceof Error ? e.message : t(lang, "error"));
    } finally { setBusy(false); }
  };

  const step = kycOutcome === "VERIFIED" ? 4 : screen === "done" || screen === "kyc" ? 3 : screen === "checkout" || screen === "quote" || quote ? 2 : 1;
  const bill = quote && (
    <Bill lang={lang} quote={quote} busy={busy} onChange={change} onShare={share} onAccept={() => setScreen("checkout")} />
  );

  let body: React.ReactNode;
  if (screen === "kyc" && order) {
    body = <Kyc lang={lang} orderId={order.id} onVerified={setKycOutcome} onToast={setToast} />;
  } else if (screen === "welcome") {
    body = <Welcome lang={lang} onStart={start} />;
  } else if (isWide) {
    const right = screen === "checkout" && quote
      ? <Checkout lang={lang} total={quote.priced.monthly_total_inr} busy={busy} error={checkoutErr}
                  onBack={() => setScreen("advisor")} onSubmit={accept} />
      : screen === "done" && order ? <Done lang={lang} order={order} onUpload={() => setScreen("kyc")} />
      : bill ?? <div className="empty-bill">{t(lang, "sampleTitle")}…</div>;
    body = (
      <div className="main split">
        <div className="pane-chat">
          <Advisor lang={lang} msgs={msgs} reply={reply} busy={busy} autoListen={autoListen} quoteTotal={null}
                   onText={sendText} onForm={sendForm} onViewQuote={() => setScreen("quote")} />
        </div>
        <aside className="pane-bill">{right}</aside>
      </div>
    );
  } else if (screen === "quote" && bill) {
    body = <div className="pane-bill">{bill}<button className="linkbtn" onClick={() => setScreen("advisor")}>{t(lang, "back")}</button></div>;
  } else if (screen === "checkout" && quote) {
    body = <Checkout lang={lang} total={quote.priced.monthly_total_inr} busy={busy} error={checkoutErr}
                     onBack={() => setScreen("quote")} onSubmit={accept} />;
  } else if (screen === "done" && order) {
    body = <Done lang={lang} order={order} onUpload={() => setScreen("kyc")} />;
  } else {
    body = <Advisor lang={lang} msgs={msgs} reply={reply} busy={busy} autoListen={autoListen}
                    quoteTotal={quote ? quote.priced.monthly_total_inr : null}
                    onText={sendText} onForm={sendForm} onViewQuote={() => setScreen("quote")} />;
  }

  return (
    <div className="app" lang={lang}>
      <Header lang={lang} setLang={setLang} onCall={callMe} />
      {screen !== "welcome" && <Journey lang={lang} step={step} />}
      <main style={{ flex: 1 }}>{body}</main>
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
