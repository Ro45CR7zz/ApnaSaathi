import { useEffect, useRef, useState } from "react";
import { CircleAlert, CircleCheck, Minus, Plus, Share2, Sparkles } from "lucide-react";
import type { Lang, Quote, QuoteChange } from "../api";
import { inr } from "../api";
import { cityName, t, unitLabel } from "../i18n";
import { Icon } from "./Icon";

export function Bill({ lang, quote, busy, onChange, onShare, onAccept }: {
  lang: Lang; quote: Quote; busy: boolean; onChange: (c: QuoteChange) => void; onShare: () => void; onAccept: () => void;
}) {
  const p = quote.priced;
  const [printing, setPrinting] = useState(true);
  const prevTotal = useRef(p.monthly_total_inr);
  const [bump, setBump] = useState(false);
  useEffect(() => { const id = setTimeout(() => setPrinting(false), 1200); return () => clearTimeout(id); }, []);
  useEffect(() => {
    if (prevTotal.current !== p.monthly_total_inr) { setBump(true); prevTotal.current = p.monthly_total_inr; const id = setTimeout(() => setBump(false), 400); return () => clearTimeout(id); }
  }, [p.monthly_total_inr]);

  const baseTerm = quote.options.commit_extra_12m ? p.contract_months - 12 : p.contract_months;
  const open = quote.status === "open";
  const where = [quote.business, cityName(quote.city, lang)].filter(Boolean).join(", ");

  return (
    <article className={`bill ${printing ? "printing" : ""}`} aria-label={t(lang, "yourQuote")}>
      <h2>{t(lang, "yourQuote")}</h2>
      <p className="who">{where}. {t(lang, "contract", { n: p.contract_months })}.</p>

      {quote.lines.map((l) => (
        <div className="line" key={l.product_id}>
          <span className="ic"><Icon name={l.icon} /></span>
          <span className="nm">{l.plain}</span>
          <span className="amt">{inr(l.monthly_inr)}</span>
          <span className="pn">{l.product_name}</span>
          {l.monthly_inr < l.list_monthly_inr ? <span className="was">{inr(l.list_monthly_inr)}</span> : <span />}
          <span className="why">{l.why}</span>
          {open && (l.adjustable_qty || l.removable) && (
            <div className="ctl">
              {l.adjustable_qty ? (
                <>
                  <span className="qty" role="group" aria-label={l.plain}>
                    <button aria-label="−" disabled={busy || l.qty <= 1} onClick={() => onChange({ set_qty: { [l.product_id]: l.qty - 1 } })}><Minus size={18} /></button>
                    <span aria-live="polite">{l.qty}</span>
                    <button aria-label="+" disabled={busy || l.qty >= l.max_qty} onClick={() => onChange({ set_qty: { [l.product_id]: l.qty + 1 } })}><Plus size={18} /></button>
                  </span>
                  <span className="qty-note">{unitLabel(l.unit, l.qty, lang)} × {inr(l.unit_price_inr)}</span>
                </>
              ) : <span className="qty-note">{l.qty} {unitLabel(l.unit, l.qty, lang)}</span>}
              {l.removable && <button className="rm" disabled={busy} onClick={() => onChange({ remove: l.product_id })}>{t(lang, "remove")}</button>}
            </div>
          )}
        </div>
      ))}

      {quote.notices.map((n) => (
        <div className="callout amber" key={n}><CircleAlert size={18} />{n}</div>
      ))}

      {open && quote.addons.length > 0 && (
        <>
          <h3 className="sect">{t(lang, "addIfNeeded")}</h3>
          {quote.addons.map((a) => (
            <div className="addon" key={a.product_id}>
              <span className="ic"><Icon name={a.icon} size={20} /></span>
              <span className="t">{a.plain}<small>{a.qty > 1 ? `${a.qty} ${unitLabel(a.unit, a.qty, lang)}, ` : ""}+{inr(a.list_monthly_inr)}{t(lang, "perMonth")}</small></span>
              <button className="addbtn" disabled={busy} onClick={() => onChange({ add: a.product_id })}><Plus size={16} />{t(lang, "add")}</button>
            </div>
          ))}
        </>
      )}

      {open && (
        <>
          <h3 className="sect">{t(lang, "waysToSave")}</h3>
          <label className="toggle">
            <input type="checkbox" checked={quote.options.commit_extra_12m} disabled={busy}
                   onChange={(e) => onChange({ commit_extra_12m: e.target.checked })} />
            <span className="sw" aria-hidden="true" />
            <span className="lbl">{t(lang, "commit", { months: baseTerm + 12, base: baseTerm })}</span>
          </label>
          {quote.selfserve_saving_available && (
            <label className="toggle">
              <input type="checkbox" checked={quote.options.selfserve_autopay} disabled={busy}
                     onChange={(e) => onChange({ selfserve_autopay: e.target.checked })} />
              <span className="sw" aria-hidden="true" />
              <span className="lbl">{t(lang, "autopay")}</span>
            </label>
          )}
          {quote.airfiber_available && (
            <label className="toggle">
              <input type="checkbox" checked={quote.using_airfiber} disabled={busy}
                     onChange={(e) => onChange({ use_airfiber: e.target.checked })} />
              <span className="sw" aria-hidden="true" />
              <span className="lbl">{t(lang, "airfiber")}</span>
            </label>
          )}
        </>
      )}

      {p.savings.length > 0 && (
        <>
          <h3 className="sect">{t(lang, "savingsEarned")}</h3>
          {p.savings.map((s) => (
            <div className="saving" key={s.code}><span><Sparkles size={16} aria-hidden="true" />{s.label}</span><span>−{inr(s.amount_inr)}</span></div>
          ))}
        </>
      )}

      <div className={`total ${bump ? "bump" : ""}`}>
        <div className="big"><span>{t(lang, "everyMonth")}</span><b aria-live="polite">{inr(p.monthly_total_inr)}</b></div>
        <div className="sub"><span>{t(lang, "inclGst", { sub: inr(p.monthly_subtotal_inr), gst: inr(p.monthly_gst_inr) })}</span></div>
        <div className="sub strong"><span>{t(lang, "oneTime")}</span><span>{inr(p.one_time_total_inr)}</span></div>
      </div>

      {quote.excluded.length > 0 && (
        <>
          <h3 className="sect">{t(lang, "notAvailable")}</h3>
          {quote.excluded.map((e) => (
            <div className="callout amber" key={e.product_id}><CircleAlert size={18} />{e.message}</div>
          ))}
        </>
      )}
      {quote.status === "accepted" && <div className="callout green"><CircleCheck size={18} />{t(lang, "orderPlaced")}: {quote.order_id}</div>}

      {open && (
        <div className="billactions">
          <button className="btn btn-primary btn-block" disabled={busy} onClick={onAccept}>{t(lang, "accept")}</button>
          <button className="btn btn-secondary btn-block" disabled={busy} onClick={onShare}><Share2 size={20} aria-hidden="true" />{t(lang, "shareWhatsApp")}</button>
        </div>
      )}
    </article>
  );
}
