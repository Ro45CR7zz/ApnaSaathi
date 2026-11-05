import { useState } from "react";
import { CircleCheck, FileUp } from "lucide-react";
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
    <section className="sheet">
      <h2>{t(lang, "checkoutTitle")}</h2>
      <p className="sub">{t(lang, "checkoutSub")}</p>
      <div className="kv" style={{ borderTop: 0 }}><span>{t(lang, "everyMonth")}</span><b>{inr(total)}</b></div>
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
        <button className="btn btn-primary btn-block" type="submit" disabled={busy || !consent}>{t(lang, "placeOrder")}</button>
        <button className="linkbtn" type="button" onClick={onBack}>{t(lang, "back")}</button>
      </form>
    </section>
  );
}

export function Done({ lang, order, onUpload }: { lang: Lang; order: Order; onUpload: () => void }) {
  return (
    <section className="sheet">
      <div className="donehead">
        <span className="ok"><CircleCheck size={30} /></span>
        <div><h2 style={{ margin: 0 }}>{t(lang, "orderPlaced")}</h2></div>
      </div>
      <div className="kv"><span>{t(lang, "orderNo")}</span><b>{order.id}</b></div>
      <div className="kv"><span>{t(lang, "expected")}</span><b>{formatDate(order.expected_activation, lang)}</b></div>
      <div className="kv"><span>{t(lang, "everyMonth")}</span><b>{inr(order.monthly_total_inr)}</b></div>
      <div className="kv"><span>{t(lang, "oneTime")}</span><b>{inr(order.one_time_total_inr)}</b></div>
      {order.lines.map((l) => (
        <div className="kv" key={l.product_id}>
          <span style={{ display: "flex", gap: 10, alignItems: "center" }}><Icon name={l.icon} size={20} />{l.plain} × {l.qty}</span>
          <b>{formatDate(l.expected_ready, lang)}</b>
        </div>
      ))}
      <p style={{ marginTop: 20 }}>{order.next_step}</p>
      <button className="btn btn-primary btn-block" onClick={onUpload}><FileUp size={22} aria-hidden="true" />{t(lang, "uploadDocs")}</button>
    </section>
  );
}
