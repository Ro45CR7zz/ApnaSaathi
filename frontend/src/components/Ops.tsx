import { useCallback, useEffect, useState } from "react";
import { api, ApiError, inr, setOpsToken } from "../api";

// Back office for sales, partners and operations (English; desktop-first, dense by design).
type Tab = "leads" | "kyc" | "calls" | "orders" | "funnel";

interface LeadRow { lead_id: string; business_name: string; business_type: string; segment: string; city: string;
  lead_source: string; stage_reached: string; drop_reason: string | null; score: number; next_best_action: string;
  offer: { recommended: string | null; options: { offer: string; label: string; expected_value_inr: number; allowed: boolean }[]; assumptions: string } | null }
interface Model { cv_auc: number; base_rate_pct: number; [k: string]: unknown }

function useOps<T>(path: string, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const reload = useCallback(() => {
    api.ops<T>(path).then((d) => { setData(d); setErr(null); }).catch((e) => setErr(e instanceof ApiError ? e.message : "Failed"));
  }, [path]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(reload, [reload, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps
  return { data, err, reload };
}

function Leads() {
  const [segment, setSegment] = useState("");
  const [stage, setStage] = useState("");
  const q = new URLSearchParams({ limit: "40", ...(segment && { segment }), ...(stage && { stage }) }).toString();
  const { data, err } = useOps<{ total: number; rows: LeadRow[]; model: Model }>(`/leads?${q}`);
  const [open, setOpen] = useState<string | null>(null);
  const m = data?.model;
  return (
    <div>
      {m && (
        <div className="ops-cards">
          <div className="card ops-card"><span>Lead score quality (5-fold CV AUC)</span><b>{m.cv_auc}</b></div>
          <div className="card ops-card"><span>Calling top 30% of leads finds</span><b>{String(m["top_30pct_leads_capture_pct_of_activations"])}% of activations</b></div>
          <div className="card ops-card"><span>Activation rate, top 20% vs all</span><b>{String(m["top_20pct_activation_rate_pct"])}% vs {m.base_rate_pct}%</b></div>
        </div>
      )}
      <div className="ops-filters">
        <select value={segment} onChange={(e) => setSegment(e.target.value)} aria-label="Segment">
          <option value="">All segments</option>
          {["Micro retail & services", "Professional offices", "Small multi-site businesses", "Small manufacturers"].map((s) => <option key={s}>{s}</option>)}
        </select>
        <select value={stage} onChange={(e) => setStage(e.target.value)} aria-label="Stage">
          <option value="">All stages</option>
          {["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete"].map((s) => <option key={s}>{s}</option>)}
        </select>
        <span className="muted">{data ? `${data.total} stalled leads, highest score first` : ""}</span>
      </div>
      {err && <p className="err">{err}</p>}
      <div className="tablewrap"><table className="ops-table">
        <thead><tr><th>Score</th><th>Business</th><th>Segment / city</th><th>Source</th><th>Stopped at</th><th>Why</th><th>Next best action</th><th>Lead with</th></tr></thead>
        <tbody>
          {data?.rows.map((r) => (
            <tr key={r.lead_id} onClick={() => setOpen(open === r.lead_id ? null : r.lead_id)}>
              <td><span className="scorebar"><i style={{ width: `${Math.min(100, r.score * 150)}%` }} /></span>{(r.score * 100).toFixed(0)}%</td>
              <td><b>{r.business_name}</b><br /><small>{r.business_type}, {r.lead_id}</small></td>
              <td>{r.segment}<br /><small>{r.city}</small></td>
              <td>{r.lead_source}</td><td>{r.stage_reached}</td><td>{r.drop_reason}</td>
              <td>{r.next_best_action}</td>
              <td>
                {r.offer?.options.find((o) => o.offer === r.offer?.recommended)?.label}
                {open === r.lead_id && r.offer && (
                  <div className="offerbox">
                    {r.offer.options.map((o) => <div key={o.offer}>{o.label}: {inr(o.expected_value_inr)} expected {o.allowed ? "" : "(below margin floor)"}</div>)}
                    <small>{r.offer.assumptions}</small>
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table></div>
    </div>
  );
}

interface QueueItem { id: string; order_id: string | null; sample_id: string | null; business: string | null; reasons: string[]; uploaded: string[] }

function KycReview() {
  const { data, err, reload } = useOps<QueueItem[]>("/kyc");
  const [sel, setSel] = useState<QueueItem | null>(null);
  const [imgs, setImgs] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    setImgs({}); setNote(""); setMsg(null);
    if (!sel) return;
    sel.uploaded.forEach((dt) => api.opsBlob(`/kyc/${sel.id}/documents/${dt}`).then((u) => setImgs((m) => ({ ...m, [dt]: u }))).catch(() => undefined));
  }, [sel]);
  const decide = async (decision: string) => {
    if (!sel) return;
    try {
      await api.ops(`/kyc/${sel.id}/decision`, "POST", { decision, note });
      setMsg(`Recorded: ${decision}`); setSel(null); reload();
    } catch (e) { setMsg(e instanceof ApiError ? e.message : "Failed"); }
  };
  return (
    <div className="ops-split">
      <div>
        {err && <p className="err">{err}</p>}
        {data && data.length === 0 && <p className="muted">No cases waiting for review.</p>}
        {data?.map((c) => (
          <button key={c.id} className={`ops-item ${sel?.id === c.id ? "on" : ""}`} onClick={() => setSel(c)}>
            <b>{c.business ?? c.id}</b><small>{c.id}{c.order_id ? `, order ${c.order_id}` : ""}{c.sample_id ? `, sample ${c.sample_id}` : ""}</small>
            <span>{c.reasons[0]}</span>
          </button>
        ))}
        {msg && <p className="muted">{msg}</p>}
      </div>
      <div>
        {sel ? (
          <div className="card ops-detail">
            <h3>{sel.business}</h3>
            <ul>{sel.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
            <p className="muted">Document views are recorded in the audit trail.</p>
            <div className="ops-docs">{Object.entries(imgs).map(([dt, u]) => <figure key={dt}><a href={u} target="_blank" rel="noreferrer"><img src={u} alt={dt} /></a><figcaption>{dt.replace("_", " ")}</figcaption></figure>)}</div>
            <label className="field"><span>Decision note (required)</span>
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Trade name confirmed on call with owner" /></label>
            <div className="row-actions">
              <button className="btn btn-primary" onClick={() => decide("approve")}>Approve</button>
              <button className="btn btn-secondary" onClick={() => decide("request_fix")}>Ask owner to fix</button>
              <button className="btn btn-secondary" onClick={() => decide("reject")}>Reject</button>
            </div>
          </div>
        ) : <p className="muted">Select a case.</p>}
      </div>
    </div>
  );
}

function Calls() {
  const h = useOps<{ id: string; known: Record<string, unknown>; language: string; channel: string; requested_at: string; score: number }[]>("/handoffs");
  const q = useOps<{ quote_id: string; business_type: string; city: string; segment: string; channel: string; lines: string[]; events: number; updated_at: string }[]>("/open-quotes");
  return (
    <div>
      <h3>Call requests from the Advisor</h3>
      <div className="tablewrap"><table className="ops-table"><thead><tr><th>Requested</th><th>Score</th><th>What we know (no personal data)</th><th>Language</th><th>Channel</th></tr></thead>
        <tbody>{h.data?.map((x) => <tr key={x.id}><td>{x.requested_at.replace("T", " ").slice(0, 16)}</td><td>{(x.score * 100).toFixed(0)}%</td>
          <td>{Object.entries(x.known).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : v}`).join("; ")}</td><td>{x.language}</td><td>{x.channel}</td></tr>)}</tbody></table></div>
      <h3>Quotes shown but not accepted</h3>
      <div className="tablewrap"><table className="ops-table"><thead><tr><th>Quote</th><th>Business</th><th>Segment</th><th>Products</th><th>Changes</th><th>Last seen</th></tr></thead>
        <tbody>{q.data?.map((x) => <tr key={x.quote_id}><td>{x.quote_id}</td><td>{x.business_type}, {x.city}</td><td>{x.segment}</td>
          <td>{x.lines.join(", ")}</td><td>{x.events}</td><td>{x.updated_at.replace("T", " ").slice(0, 16)}</td></tr>)}</tbody></table></div>
    </div>
  );
}

function Orders() {
  const { data, reload } = useOps<{ id: string; state: string; business_type: string; city: string; monthly_total_inr: number; created_at: string }[]>("/orders");
  const [msg, setMsg] = useState<string | null>(null);
  const sim = async (id: string, event: string, reason = "technician") => {
    try { const r = await api.ops<{ state: string }>(`/orders/${id}/simulate`, "POST", { event, reason }); setMsg(`${id}: ${r.state}`); reload(); }
    catch (e) { setMsg(e instanceof ApiError ? `${id}: ${e.message}` : "Failed"); }
  };
  return (
    <div>
      <p className="muted">Simulated field events for the demo (labelled; production would receive these from field-force and provisioning systems).</p>
      {msg && <p className="muted"><b>{msg}</b></p>}
      <div className="tablewrap"><table className="ops-table"><thead><tr><th>Order</th><th>Business</th><th>Monthly</th><th>State</th><th>Simulate</th></tr></thead>
        <tbody>{data?.map((o) => (
          <tr key={o.id}><td><a href={`#/track/${o.id}`} target="_blank" rel="noreferrer">{o.id}</a></td><td>{o.business_type}, {o.city}</td>
            <td>{inr(o.monthly_total_inr)}</td><td><code>{o.state}</code></td>
            <td className="simbtns">
              <button onClick={() => sim(o.id, "advance")}>Next step</button>
              <button onClick={() => sim(o.id, "delay")}>Delay 3 days</button>
              <button onClick={() => sim(o.id, "feasibility_failed")}>Fibre not feasible</button>
              <button onClick={() => sim(o.id, "payment_failed")}>Payment fails</button>
            </td></tr>))}</tbody></table></div>
    </div>
  );
}

function Funnel() {
  const { data } = useOps<{ baseline_q2_2026: { stage: string; count: number }[]; live_prototype: { stage: string; count: number }[] }>("/funnel");
  const bars = (rows: { stage: string; count: number }[]) => {
    const max = Math.max(1, ...rows.map((r) => r.count));
    return rows.map((r, i) => (
      <div className="fbar" key={r.stage}><span>{r.stage}</span>
        <i style={{ width: `${(100 * r.count) / max}%` }} /><b>{r.count.toLocaleString("en-IN")}</b>
        <small>{i > 0 && rows[i - 1].count ? `${Math.round((100 * r.count) / rows[i - 1].count)}%` : ""}</small></div>
    ));
  };
  return (
    <div className="ops-split even">
      <div className="card card-pad"><h3 style={{ marginTop: 0 }}>Baseline: Apr to Jun 2026 (smb_leads.csv)</h3>{data && bars(data.baseline_q2_2026)}</div>
      <div className="card card-pad funnel-live"><h3 style={{ marginTop: 0 }}>apnaSaathi prototype (live)</h3>{data && bars(data.live_prototype)}</div>
    </div>
  );
}

export function Ops() {
  const [token, setToken] = useState<string | null>(() => { try { return sessionStorage.getItem("ops.token"); } catch { return null; } });
  const [input, setInput] = useState("");
  const [tab, setTab] = useState<Tab>("leads");
  setOpsToken(token); // set before children fetch (child effects run before parent effects)
  if (!token) {
    return (
      <section className="card card-pad ops-login">
        <h2>Back office</h2>
        <p className="card-sub">For Accel sales, partners and operations. Prototype access uses a demo token (OPS_TOKEN in .env).</p>
        <form onSubmit={(e) => { e.preventDefault(); try { sessionStorage.setItem("ops.token", input); } catch { /* ignore */ } setToken(input); }}>
          <div className="field"><label htmlFor="tok">Access token</label><input id="tok" type="password" value={input} onChange={(e) => setInput(e.target.value)} /></div>
          <button className="btn btn-primary btn-block" type="submit">Open back office</button>
        </form>
      </section>
    );
  }
  const tabs: [Tab, string][] = [["leads", "Leads to call"], ["kyc", "KYC review"], ["calls", "Call requests"], ["orders", "Orders"], ["funnel", "Funnel"]];
  return (
    <section className="ops">
      <nav className="ops-tabs" role="tablist">
        {tabs.map(([k, label]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{label}</button>)}
        <button className="linkbtn" style={{ marginLeft: "auto" }} onClick={() => { try { sessionStorage.removeItem("ops.token"); } catch { /* */ } setToken(null); }}>Sign out</button>
      </nav>
      <div className="ops-body">
        {tab === "leads" && <Leads />}{tab === "kyc" && <KycReview />}{tab === "calls" && <Calls />}
        {tab === "orders" && <Orders />}{tab === "funnel" && <Funnel />}
      </div>
    </section>
  );
}
