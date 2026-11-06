import { useCallback, useEffect, useState } from "react";
import { BellRing, Check, CircleAlert, CircleDot, PhoneCall, RefreshCw, Wallet } from "lucide-react";
import { api, inr, type Lang, type Tracker as TrackerT } from "../api";
import { formatDate, t, type Key } from "../i18n";

const shortDate = (iso: string, lang: Lang) =>
  new Date(iso + "T00:00:00").toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short" });
import { Icon } from "./Icon";

export function Tracker({ lang, orderId, onFixDocs, onCall }: {
  lang: Lang; orderId: string; onFixDocs: () => void; onCall: () => void;
}) {
  const [tr, setTr] = useState<TrackerT | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => api.tracker(orderId).then(setTr).catch(() => setErr(t(lang, "error"))), [orderId, lang]);
  useEffect(() => { load(); const id = setInterval(load, 5000); return () => clearInterval(id); }, [load]);

  if (!tr) return <section className="page"><p className="muted">{err ?? "…"}</p></section>;
  const act = async (fn: () => Promise<TrackerT>) => {
    setBusy(true); setErr(null);
    try { setTr(await fn()); } catch (e) { setErr(e instanceof Error ? e.message : t(lang, "error")); } finally { setBusy(false); }
  };
  const L = (k: Key, v?: Record<string, string | number>) => t(lang, k, v);
  const p = tr.pending[0];

  const stamp = (at: string) => new Date(at).toLocaleString(lang === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

  return (
    <section className="page">
      <div className="track-hero">
        <div style={{ position: "relative", zIndex: 1 }}>
          <div className="ord"><span className="pill">{L("orderLabel")} {tr.order_id}</span>{tr.business}</div>
          <span className="lbl">{L("readyBy")}</span>
          <h1>{formatDate(tr.expected_activation, lang)}</h1>
        </div>
        <div className="meta">
          <span>{L("everyMonth")}</span>
          <b>{inr(tr.bill.monthly_total_inr)}</b>
        </div>
        <button className="iconbtn" onClick={load} aria-label={L("refresh")}><RefreshCw size={17} /></button>
      </div>

      <ol className="card steps-h">
        {tr.steps.map((s) => (
          <li key={s.key} className={`tl-${s.status}`}>
            <span className="node" aria-hidden="true">
              {s.status === "done" ? <Check size={16} strokeWidth={3} /> : s.status === "attention" ? <CircleAlert size={16} /> : <CircleDot size={16} />}
            </span>
            <span className="tl-label">{s.label}</span>
            <span className="tl-date">{s.date ? shortDate(s.date, lang) : ""}</span>
          </li>
        ))}
      </ol>

      <div className="track-grid">
        <div className="track-col">
          <div className={`card card-pad todo ${p && p.kind !== "wait" ? "todo-act" : ""}`}>
            <h3>{p && p.kind !== "wait" ? <CircleAlert size={20} color="var(--primary)" aria-hidden="true" /> : <Check size={20} color="var(--green)" aria-hidden="true" />}{L("todo")}</h3>
            {err && <p className="err" role="alert">{err}</p>}
            <p>{p ? p.text : L("nothingTodo")}</p>
            {p && (p.kind === "pay" || p.kind === "retry_payment") && (
              <>
                <button className="btn btn-primary btn-block btn-lg" disabled={busy} onClick={() => act(() => api.pay(orderId))}>
                  <Wallet size={20} aria-hidden="true" />{L("payNow", { amt: inr(p.amount_inr ?? 0) })}
                </button>
                <p className="hint">{L("payDemo")}</p>
              </>
            )}
            {p && (p.kind === "upload_documents" || p.kind === "fix_documents") && (
              <button className="btn btn-primary btn-block btn-lg" onClick={onFixDocs}>{L(p.kind === "fix_documents" ? "fixDocs" : "uploadNow")}</button>
            )}
            {p && p.kind === "switch_airfiber" && (
              <button className="btn btn-primary btn-block btn-lg" disabled={busy} onClick={() => act(() => api.switchAirfiber(orderId))}>{L("switchNow")}</button>
            )}
            {p && p.kind === "call_us" && (
              <button className="btn btn-secondary btn-block btn-lg" onClick={onCall}><PhoneCall size={20} aria-hidden="true" />{L("callMe")}</button>
            )}
          </div>

          <div className="card card-pad">
            <h3>{L("services")}</h3>
            {tr.lines.map((l) => (
              <div className="svc" key={l.product_id}>
                <span className="ic"><Icon name={l.icon} size={20} /></span>
                <span className="nm">{l.plain} × {l.qty}
                  {l.state !== "ACTIVE" && l.state !== "CANCELLED" && <small>{L("expected")}: {shortDate(l.expected_ready, lang)}</small>}</span>
                <span className={`pill p-${l.state}`}>{L(`st_${l.state}` as Key)}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="track-col">
          <div className="card card-pad">
            <h3>{L("yourBill")}</h3>
            <div className="kv" style={{ marginTop: 8 }}><span>{L("everyMonth")}</span><b>{inr(tr.bill.monthly_total_inr)}</b></div>
            <div className="kv"><span>{L("oneTime")}</span><b>{inr(tr.bill.one_time_total_inr)}</b></div>
            <div className="kv"><span>{L("contract", { n: tr.bill.contract_months })}</span><b>{tr.bill.next_bill_date ? `${L("nextBill")}: ${shortDate(tr.bill.next_bill_date, lang)}` : ""}</b></div>
          </div>
          {tr.notifications.length > 0 && (
            <div className="card card-pad">
              <h3 style={{ display: "flex", gap: 8, alignItems: "center" }}><BellRing size={18} aria-hidden="true" />{L("updates")}</h3>
              <ul className="updates">
                {tr.notifications.map((n, i) => <li key={i}><span>{n.text}<small>{stamp(n.at)}</small></span></li>)}
              </ul>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
