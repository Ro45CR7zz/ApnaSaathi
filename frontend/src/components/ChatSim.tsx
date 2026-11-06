import { useEffect, useRef, useState } from "react";
import { api, type Lang } from "../api";
import { Icon } from "./Icon";

type Bubble = { me: boolean; text: string; link?: string | null; at: string };
const SENDER = "sim:+91-demo-0001";
const clock = () => new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });

/** Messaging-channel simulator: talks to the same webhook a WhatsApp Business number would use. */
export function ChatSim({ lang }: { lang: Lang }) {
  const [items, setItems] = useState<Bubble[]>([]);
  const [chips, setChips] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const hi = lang === "hi";

  const send = async (t: string, show = true) => {
    if (!t.trim() || busy) return;
    if (show) setItems((m) => [...m, { me: true, text: t, at: clock() }]);
    setText(""); setChips([]); setBusy(true);
    try {
      const r = await api.channelMessage(SENDER, t, lang);
      const link = r.quote_link ? `#/q/${r.quote_id}` : null;
      const body = r.quote_link ? r.reply.replace(r.quote_link, "").trimEnd() : r.reply;
      setItems((m) => [...m, { me: false, text: body, link, at: clock() }]);
      setChips(r.quick_replies);
    } catch {
      setItems((m) => [...m, { me: false, text: hi ? "माफ़ कीजिए, कुछ गड़बड़ हुई। फिर से भेजें।" : "Sorry, something went wrong. Please send again.", at: clock() }]);
    } finally { setBusy(false); }
  };

  const restart = () => { setItems([]); send(hi ? "नया" : "restart", false); };
  useEffect(() => { restart(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [lang]);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [items, chips]);

  return (
    <div className="sim">
      <p className="sim-note">{hi ? "डेमो: मैसेजिंग चैनल सिम्युलेटर। यही बातचीत एक असली WhatsApp Business नंबर से जुड़ सकती है।"
        : "Demo: messaging channel simulator. The same conversation can be connected to a real WhatsApp Business number."}</p>
      <div className="sim-phone">
        <div className="sim-top">
          <span className="sim-av"><Icon name="message-square-text" size={20} /></span>
          <div><b>Accel Business</b><small>{hi ? "apnaSaathi सहायक" : "apnaSaathi assistant"}</small></div>
          <button className="sim-restart" onClick={restart} aria-label={hi ? "फिर से शुरू करें" : "Start again"}><Icon name="rotate-ccw" size={18} /></button>
        </div>
        <div className="sim-feed">
          {items.map((b, i) => (
            <div key={i} className={b.me ? "sb sb-me" : "sb sb-them"}>
              {b.text}
              {b.link && <a className="sim-link" href={b.link}>{hi ? "कोटेशन खोलें" : "Open quote"} →</a>}
              <time>{b.at}</time>
            </div>
          ))}
          {busy && <div className="sb sb-them sb-typing" aria-label="typing"><i /><i /><i /></div>}
          <div ref={end} />
        </div>
        {chips.length > 0 && (
          <div className="sim-chips">{chips.map((c) => <button key={c} onClick={() => send(c)} disabled={busy}>{c}</button>)}</div>
        )}
        <form className="sim-input" onSubmit={(e) => { e.preventDefault(); send(text); }}>
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder={hi ? "मैसेज लिखें" : "Type a message"} maxLength={500} />
          <button type="submit" disabled={busy || !text.trim()} aria-label={hi ? "भेजें" : "Send"}><Icon name="send" size={20} /></button>
        </form>
      </div>
    </div>
  );
}
