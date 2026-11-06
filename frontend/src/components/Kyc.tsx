import { useEffect, useRef, useState } from "react";
import { BadgeCheck, Camera, ChevronDown, CircleAlert, CircleCheck, Eye, FileText, FlaskConical, IdCard, Lock, Receipt, Search, ShieldCheck, Trash2, UserCheck } from "lucide-react";
import { api, type GstinResult, type KycCase, type Lang, type Sample } from "../api";
import { t, type Key } from "../i18n";

const DOC_META: Record<string, { icon: React.ReactNode; en: string; hi: string }> = {
  gst_certificate: { icon: <FileText />, en: "GST certificate", hi: "GST सर्टिफ़िकेट" },
  udyam_certificate: { icon: <BadgeCheck />, en: "Udyam certificate", hi: "उद्यम सर्टिफ़िकेट" },
  address_proof: { icon: <Receipt />, en: "Electricity bill (last 3 months)", hi: "बिजली का बिल (पिछले 3 महीने का)" },
  signatory_id: { icon: <IdCard />, en: "ID of the person signing", hi: "हस्ताक्षर करने वाले की ID" },
};

function DocSlot({ lang, kase, docType, busy, onUpload }: {
  lang: Lang; kase: KycCase; docType: string; busy: boolean; onUpload: (dt: string, f: File) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const meta = DOC_META[docType];
  const up = kase.uploaded[docType];
  const good = !!up && up.sharp && up.readable;
  const state = !up ? null
    : !up.sharp ? <span className="pill amber"><CircleAlert size={13} />{t(lang, "blurry")}</span>
    : !up.readable ? <span className="pill amber"><CircleAlert size={13} />{t(lang, "unreadable")}</span>
    : <span className="pill green"><CircleCheck size={13} />{t(lang, "uploaded")}</span>;
  return (
    <div className={`doc ${good ? "ok" : up ? "warn" : ""}`}>
      <div className="doc-img">
        <img src={`/api/kyc/specimen/${docType}.png`} alt={`${t(lang, "looksLike")}: ${meta[lang]}`} loading="lazy" />
        {state}
        {!up && <span className="lk">{t(lang, "looksLike")}</span>}
      </div>
      <div className="doc-body">
        <div className="doc-name">{meta.icon}{meta[lang]}</div>
        <input ref={ref} type="file" accept="image/*" capture="environment" hidden
               onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(docType, f); e.target.value = ""; }} />
        <button className={`btn btn-block ${good ? "btn-secondary" : "btn-primary"}`} disabled={busy} onClick={() => ref.current?.click()}>
          <Camera size={18} aria-hidden="true" />{up ? t(lang, "retake") : t(lang, "takePhoto")}
        </button>
      </div>
    </div>
  );
}

export function Kyc({ lang, orderId, onVerified, onToast, onTrack }: {
  lang: Lang; orderId: string; onVerified: (outcome: string) => void; onToast: (s: string) => void; onTrack: () => void;
}) {
  const [kase, setKase] = useState<KycCase | null>(null);
  const [busy, setBusy] = useState(false);
  const [agree, setAgree] = useState<Record<string, boolean>>({});
  const [gstin, setGstin] = useState("");
  const [gstRes, setGstRes] = useState<GstinResult | null>(null);
  const [udyam, setUdyam] = useState("");
  const [samples, setSamples] = useState<Sample[]>([]);
  const [sample, setSample] = useState("K12");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.kycCreate(orderId, lang).then(setKase).catch(() => setErr(t(lang, "error")));
    api.kycSamples().then(setSamples).catch(() => undefined);
  }, [orderId]); // eslint-disable-line react-hooks/exhaustive-deps

  const run = async <T,>(fn: () => Promise<T>, then: (x: T) => void) => {
    setBusy(true); setErr(null);
    try { then(await fn()); } catch (e) { setErr(e instanceof Error ? e.message : t(lang, "error")); } finally { setBusy(false); }
  };

  if (!kase) return <section className="page"><p className="muted">{err ?? "…"}</p></section>;

  const L = (k: Key, v?: Record<string, string | number>) => t(lang, k, v);
  const head = (
    <header className="page-head">
      <h1>{L("kycTitle")}</h1>
      <p>{L("kycSub")}</p>
    </header>
  );

  // Step A: consent, per purpose.
  if (!kase.consent_given) {
    return (
      <section className="page narrow">
        {head}
        <div className="card card-pad consentcard">
          <h3 style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}><ShieldCheck size={22} color="var(--green)" aria-hidden="true" />{L("consentTitle")}</h3>
          <p>{L("consentWhat")}</p>
          <p><Lock size={16} aria-hidden="true" />{L("consentWhere")}</p>
          <p><Trash2 size={16} aria-hidden="true" />{L("consentKeep", { days: kase.retention_days })}</p>
          <div className="purpose">
            {kase.purposes.map((p) => (
              <label className="check" key={p} style={{ marginBottom: 8 }}>
                <input type="checkbox" checked={!!agree[p]} onChange={(e) => setAgree({ ...agree, [p]: e.target.checked })} />
                <span style={{ color: "var(--ink)" }}>{L(`purpose_${p}` as Key)}</span>
              </label>
            ))}
          </div>
          {err && <p className="err" role="alert">{err}</p>}
          <button className="btn btn-primary btn-block btn-lg" disabled={busy || !kase.purposes.every((p) => agree[p])}
                  onClick={() => run(() => api.kycConsent(kase.id, kase.purposes, kase.notice_version), setKase)}>
            {L("agree")}
          </button>
          <p className="hint">{L("mockNote")}</p>
        </div>
      </section>
    );
  }

  const docsReady = kase.required_docs.every((d) => kase.uploaded[d]);
  const failing = kase.checks.filter((c) => c.status === "fail");
  const others = kase.checks.filter((c) => c.status !== "fail");
  const gstDone = !!(kase.gstin_masked || kase.no_gstin);

  const submitGstin = (value: string | null, no = false) =>
    run(() => api.kycGstin(kase.id, value, no), (r) => { setGstRes(r); if (r.case) setKase(r.case); });

  return (
    <section className="page">
      {head}
      <div className="kyc-grid">
        <div className="kyc-main">
          {err && <p className="err" role="alert">{err}</p>}

          {kase.outcome && (
            <div className={`outcome o-${kase.outcome}`} role="status">
              <span className="oi">{kase.outcome === "VERIFIED" ? <UserCheck size={22} /> : kase.outcome === "MANUAL_REVIEW" ? <Eye size={22} /> : <CircleAlert size={22} />}</span>
              <div><b>{L(`out_${kase.outcome}` as Key)}</b><span>{L(`outSub_${kase.outcome}` as Key)}</span>
                {kase.order_id && <div><button className="linkbtn" onClick={onTrack}>{L("trackOrder")}</button></div>}</div>
            </div>
          )}
          {failing.length > 0 && (
            <div className="card fixlist">
              <ul className="checklist">{failing.map((c, i) => (
                <li key={i} className={`c-${c.action}`}><CircleAlert size={18} aria-hidden="true" />{c.message}</li>))}
              </ul>
            </div>
          )}

          {/* Step 1: GST number with registry pre-fill */}
          <div className="card card-pad">
            <div className="stephead">
              <span className={`n ${gstDone ? "ok" : ""}`}>{gstDone ? <CircleCheck size={16} /> : 1}</span>
              <div><h3>{L("gstQ")}</h3><p>{L("stepGstSub")}</p></div>
            </div>
            {kase.gstin_masked ? (
              <div className="prefill">
                <span className="q">{L("isThisYou")}</span>
                <b>{kase.gst_prefill?.trade_name}</b>
                <span>{kase.gst_prefill?.legal_name}</span>
                <span>{kase.gst_prefill?.address}</span>
                <span className={kase.gst_prefill?.status === "Active" ? "pill green" : "pill amber"}>
                  {kase.gst_prefill?.status === "Active" ? <CircleCheck size={13} /> : <CircleAlert size={13} />}GSTIN {kase.gstin_masked}: {kase.gst_prefill?.status}
                </span>
              </div>
            ) : kase.no_gstin ? (
              <p className="note plain">{L("noGst")}</p>
            ) : (
              <>
                <div className="inline">
                  <label className="sr-only" htmlFor="gst">{L("gstQ")}</label>
                  <input id="gst" className="textin mono" maxLength={15} value={gstin} placeholder={L("gstPlaceholder")}
                         onChange={(e) => setGstin(e.target.value.toUpperCase().replace(/[^0-9A-Z]/g, ""))} autoComplete="off" />
                  <button className="btn btn-dark" disabled={busy || gstin.length !== 15} onClick={() => submitGstin(gstin)}>
                    <Search size={18} aria-hidden="true" />{L("check")}
                  </button>
                </div>
                {gstRes && gstRes.status === "confirm" && gstRes.suggestion && (
                  <div className="note amber" style={{ marginTop: 10 }}><CircleAlert size={18} />
                    <span>{L("didYouMean", { s: gstRes.suggestion })}{" "}
                      <button className="linkbtn" onClick={() => { setGstin(gstRes.suggestion!); submitGstin(gstRes.suggestion!); }}>{L("yesThat")}</button>
                    </span>
                  </div>
                )}
                {gstRes && ["invalid", "not_found"].includes(gstRes.status) && (
                  <div className="note amber" style={{ marginTop: 10 }}><CircleAlert size={18} />{gstRes.message}</div>
                )}
                <button className="linkbtn" onClick={() => submitGstin(null, true)}>{L("noGst")}</button>
              </>
            )}
            <div className="udyam">
              {kase.udyam_masked ? (
                <div className="done"><BadgeCheck size={18} color="var(--green)" aria-hidden="true" /><span className="mono">{kase.udyam_masked}</span></div>
              ) : (
                <div className="inline">
                  <label className="sr-only" htmlFor="udy">{L("udyamQ")}</label>
                  <input id="udy" className="textin mono" value={udyam} placeholder={L("udyamQ")}
                         onChange={(e) => setUdyam(e.target.value.toUpperCase())} autoComplete="off" />
                  <button className="btn btn-secondary" disabled={busy || udyam.length < 10}
                          onClick={() => run(() => api.kycUdyam(kase.id, udyam), setKase)}>{L("save")}</button>
                </div>
              )}
            </div>
          </div>

          {/* Step 2: documents, each with a picture of what it looks like */}
          {gstDone && (
            <div className="card card-pad">
              <div className="stephead">
                <span className={`n ${kase.outcome === "VERIFIED" ? "ok" : ""}`}>{kase.outcome === "VERIFIED" ? <CircleCheck size={16} /> : 2}</span>
                <div><h3>{L("docsTitle")}</h3><p>{L("stepDocsSub")} {L("docsHint")}</p></div>
              </div>
              <div className="docgrid">
                {kase.required_docs.map((d) => (
                  <DocSlot key={d} lang={lang} kase={kase} docType={d} busy={busy}
                           onUpload={(dt, f) => run(() => api.kycUpload(kase.id, dt, f), setKase)} />
                ))}
              </div>
              <button className="btn btn-primary btn-block btn-lg" style={{ marginTop: 16 }} disabled={busy || !docsReady}
                      onClick={() => run(() => api.kycEvaluate(kase.id), (c) => { setKase(c); if (c.outcome) onVerified(c.outcome); })}>
                {busy ? L("checking") : L("checkDocs")}
              </button>
            </div>
          )}

          {others.length > 0 && (
            <details className="card card-pad checks">
              <summary><CircleCheck size={20} color="var(--green)" aria-hidden="true" />{L("whatWeChecked")} ({others.length})<ChevronDown size={20} className="chev" aria-hidden="true" /></summary>
              <ul className="checklist">{others.map((c, i) => (
                <li key={i} className={`c-${c.status}`}>{c.status === "pass" ? <CircleCheck size={18} /> : <CircleAlert size={18} />}{c.message}</li>))}
              </ul>
            </details>
          )}
        </div>

        <aside className="kyc-aside">
          <div className="card card-pad privacy">
            <h3><ShieldCheck size={20} aria-hidden="true" />{L("privacyTitle")}</h3>
            <ul>
              <li><Lock size={16} aria-hidden="true" />{L("privacyRead")}</li>
              <li><Eye size={16} aria-hidden="true" />{L("privacyEnc")}</li>
              <li><Trash2 size={16} aria-hidden="true" />{L("privacyDel", { days: kase.retention_days })}</li>
            </ul>
            <button className="linkbtn" disabled={busy}
                    onClick={() => run(() => api.kycWithdraw(kase.id), (c) => { setKase(c); onToast(L("deleted")); })}>{L("deleteDocs")}</button>
          </div>
          {samples.length > 0 && (
            <div className="card card-pad demo">
              <h3><FlaskConical size={18} aria-hidden="true" />{L("demoTitle")}</h3>
              <p className="hint" style={{ margin: "4px 0 12px" }}>{L("demoSub")}</p>
              <div className="inline">
                <label className="sr-only" htmlFor="smp">{L("demoTitle")}</label>
                <select id="smp" className="textin" value={sample} onChange={(e) => setSample(e.target.value)}>
                  {samples.map((s) => <option key={s.id} value={s.id}>{s.id}: {s.business}, {s.city}</option>)}
                </select>
                <button className="btn btn-secondary" disabled={busy}
                        onClick={() => run(() => api.kycUseSample(kase.id, sample), (c) => { setKase(c); if (c.outcome) onVerified(c.outcome); })}>
                  {L("run")}
                </button>
              </div>
            </div>
          )}
          <p className="hint" style={{ margin: "0 4px" }}>{L("mockNote")}</p>
        </aside>
      </div>
    </section>
  );
}
