import { useState } from "react";
import { CircleCheck, FileUp, ShieldCheck } from "lucide-react";
import type { Lang, Order } from "../api";
import { inr } from "../api";
import { formatDate, t } from "../i18n";
import { Icon } from "./Icon";

export function Checkout({ lang, total, busy, error, onBack, onSubmit }: {
  lang: Lang; total: number; busy: boolean; error: string | null; onBack: () => void;
  onSubmit: (name: string, mobile: string, consent: boolean) => void;
}) {
  const [name, setName] = useState("");
  const [mobile, setMobile] = useState("");
  const [consent, setConsent] = useState(false);
  return (
    <section className="card card-pad formcard">
      <h2>{t(lang, "checkoutTitle")}</h2>
      <p className="card-sub">{t(lang, "checkoutSub")}</p>
      <div className="paybox"><span>{t(lang, "checkoutPay")}</span><b>{inr(total)}</b></div>
      <form onSubmit={(e) => { e.preventDefault(); onSubmit(name, mobile, consent); }}>
        {error && <p className="err" role="alert">{error}</p>}
        <div className="field">
          <label htmlFor="nm">{t(lang, "name")}</label>
          <input id="nm" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required minLength={2} />
        </div>
        <div className="field">
          <label htmlFor="mb">{t(lang, "mobile")}</label>
          <input id="mb" value={mobile} onChange={(e) => setMobile(e.target.value)} inputMode="numeric" autoComplete="tel" placeholder="98765 43210" required />
        </div>
        <label className="check">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          <span>{t(lang, "consent")}</span>
        </label>
        <button className="btn btn-primary btn-block btn-lg" type="submit" disabled={busy || !consent}>{t(lang, "placeOrder")}</button>
        <p className="hint" style={{ display: "flex", gap: 8 }}><ShieldCheck size={16} aria-hidden="true" style={{ flex: "none", marginTop: 3 }} />{t(lang, "privacyLine")}</p>
        <div className="backrow"><button className="linkbtn" type="button" onClick={onBack}>{t(lang, "back")}</button></div>
      </form>
    </section>
  );
}

export function Done({ lang, order, onUpload, onTrack }: { lang: Lang; order: Order; onUpload: () => void; onTrack: () => void }) {
  return (
    <section className="card card-pad donecard">
      <div className="donehead">
        <span className="ok"><CircleCheck size={28} /></span>
        <div><h2>{t(lang, "orderPlaced")}</h2><p>{t(lang, "orderNo")}: <b style={{ color: "var(--ink)" }}>{order.id}</b></p></div>
      </div>
      <div className="kv"><span>{t(lang, "expected")}</span><b>{formatDate(order.expected_activation, lang)}</b></div>
      <div className="kv"><span>{t(lang, "everyMonth")}</span><b>{inr(order.monthly_total_inr)}</b></div>
      <div className="kv"><span>{t(lang, "oneTime")}</span><b>{inr(order.one_time_total_inr)}</b></div>
      <h3 className="sect">{t(lang, "services")}</h3>
      {order.lines.map((l) => (
        <div className="kv" key={l.product_id}>
          <span><span className="ic"><Icon name={l.icon} size={18} /></span>{l.plain} × {l.qty}</span>
          <b>{formatDate(l.expected_ready, lang)}</b>
        </div>
      ))}
      <div className="note plain nextstep"><FileUp size={18} aria-hidden="true" />{order.next_step}</div>
      <button className="btn btn-primary btn-block btn-lg" onClick={onUpload}><FileUp size={20} aria-hidden="true" />{t(lang, "uploadDocs")}</button>
      <div className="backrow"><button className="linkbtn" onClick={onTrack}>{t(lang, "trackOrder")}</button></div>
    </section>
  );
}
