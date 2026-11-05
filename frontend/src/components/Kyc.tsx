import { useEffect, useRef, useState } from "react";
import { BadgeCheck, Camera, CircleAlert, CircleCheck, FileText, IdCard, Lock, Receipt, Search, ShieldCheck, UserCheck } from "lucide-react";
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
  let state: React.ReactNode = null;
  if (up) {
    state = !up.sharp ? <span className="docstate amber"><CircleAlert size={16} />{t(lang, "blurry")}</span>
      : !up.readable ? <span className="docstate amber"><CircleAlert size={16} />{t(lang, "unreadable")}</span>
      : <span className="docstate green"><CircleCheck size={16} />{t(lang, "uploaded")}</span>;
  }
  return (
    <div className="docslot">
      <img className="specimen" src={`/api/kyc/specimen/${docType}.png`} alt={`${t(lang, "looksLike")}: ${meta[lang]}`} loading="lazy" />
      <div className="docinfo">
        <div className="docname"><span className="ic">{meta.icon}</span>{meta[lang]}</div>
        {state}
        <input ref={ref} type="file" accept="image/*" capture="environment" hidden
               onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(docType, f); e.target.value = ""; }} />
        <button className={`btn ${up && up.sharp && up.readable ? "btn-secondary" : "btn-primary"}`} disabled={busy}
                onClick={() => ref.current?.click()}>
          <Camera size={20} aria-hidden="true" />{up ? t(lang, "retake") : t(lang, "takePhoto")}
        </button>
      </div>
    </div>
  );
}

export function Kyc({ lang, orderId, onVerified, onToast }: {
  lang: Lang; orderId: string; onVerified: (outcome: string) => void; onToast: (s: string) => void;
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

  if (!kase) return <section className="sheet"><p>{err ?? "…"}</p></section>;

  const L = (k: Key, v?: Record<string, string | number>) => t(lang, k, v);

  // Step A: consent, per purpose.
  if (!kase.consent_given) {
    return (
      <section className="sheet">
        <h2>{L("kycTitle")}</h2>
        <p className="sub">{L("kycSub")}</p>
        <div className="consent">
          <h3><ShieldCheck size={22} aria-hidden="true" />{L("consentTitle")}</h3>
          <p>{L("consentWhat")}</p>
          <p><Lock size={16} aria-hidden="true" /> {L("consentWhere")}</p>
          <p>{L("consentKeep", { days: kase.retention_days })}</p>
          {kase.purposes.map((p) => (
            <label className="check" key={p}>
              <input type="checkbox" checked={!!agree[p]} onChange={(e) => setAgree({ ...agree, [p]: e.target.checked })} />
              <span>{L(`purpose_${p}` as Key)}</span>
            </label>
          ))}
          {err && <p className="err" role="alert">{err}</p>}
          <button className="btn btn-primary btn-block" disabled={busy || !kase.purposes.every((p) => agree[p])}
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

  const submitGstin = (value: string | null, no = false) =>
    run(() => api.kycGstin(kase.id, value, no), (r) => { setGstRes(r); if (r.case) setKase(r.case); });

  return (
    <section className="sheet">
      <h2>{L("kycTitle")}</h2>
      <p className="sub">{L("kycSub")}</p>
      {err && <p className="err" role="alert">{err}</p>}

      {kase.outcome && (
        <div className={`outcome o-${kase.outcome}`} role="status">
          {kase.outcome === "VERIFIED" ? <UserCheck size={28} /> : <CircleAlert size={28} />}
          <div><b>{L(`out_${kase.outcome}` as Key)}</b><span>{L(`outSub_${kase.outcome}` as Key)}</span></div>
        </div>
      )}
      {failing.length > 0 && (
        <ul className="checklist">{failing.map((c, i) => (
          <li key={i} className={`c-${c.action}`}><CircleAlert size={18} aria-hidden="true" />{c.message}</li>))}
        </ul>
      )}

      {/* Step B: GST number with registry pre-fill */}
      <div className="kblock">
        <h3>{L("gstQ")}</h3>
        {kase.gstin_masked ? (
          <div className="prefill">
            <p className="hint" style={{ marginTop: 0 }}>{L("isThisYou")}</p>
            <b>{kase.gst_prefill?.trade_name}</b>
            <span>{kase.gst_prefill?.legal_name}</span>
            <span>{kase.gst_prefill?.address}</span>
            <span className={kase.gst_prefill?.status === "Active" ? "tag green" : "tag amber"}>
              GSTIN {kase.gstin_masked}: {kase.gst_prefill?.status}
            </span>
          </div>
        ) : kase.no_gstin ? (
          <p className="hint">{L("noGst")}</p>
        ) : (
          <>
            <div className="inline">
              <label className="sr-only" htmlFor="gst">{L("gstQ")}</label>
              <input id="gst" className="textin mono" maxLength={15} value={gstin} placeholder={L("gstPlaceholder")}
                     onChange={(e) => setGstin(e.target.value.toUpperCase().replace(/[^0-9A-Z]/g, ""))} autoComplete="off" />
              <button className="btn btn-primary" disabled={busy || gstin.length !== 15} onClick={() => submitGstin(gstin)}>
                <Search size={20} aria-hidden="true" />{L("check")}
              </button>
            </div>
            {gstRes && gstRes.status === "confirm" && gstRes.suggestion && (
              <div className="callout amber"><CircleAlert size={18} />
                <span>{L("didYouMean", { s: gstRes.suggestion })}{" "}
                  <button className="linkbtn" onClick={() => { setGstin(gstRes.suggestion!); submitGstin(gstRes.suggestion!); }}>{L("yesThat")}</button>
                </span>
              </div>
            )}
            {gstRes && ["invalid", "not_found"].includes(gstRes.status) && (
              <div className="callout amber"><CircleAlert size={18} />{gstRes.message}</div>
            )}
            <button className="linkbtn" onClick={() => submitGstin(null, true)}>{L("noGst")}</button>
          </>
        )}
        <div className="inline" style={{ marginTop: 12 }}>
          <label className="sr-only" htmlFor="udy">{L("udyamQ")}</label>
          <input id="udy" className="textin mono" value={kase.udyam_masked ?? udyam} disabled={!!kase.udyam_masked}
                 placeholder={L("udyamQ")} onChange={(e) => setUdyam(e.target.value.toUpperCase())} autoComplete="off" />
          {!kase.udyam_masked && (
            <button className="btn btn-secondary" disabled={busy || udyam.length < 10}
                    onClick={() => run(() => api.kycUdyam(kase.id, udyam), setKase)}>{L("save")}</button>
          )}
        </div>
      </div>

      {/* Step C: documents, each with a picture of what it looks like */}
      {(kase.gstin_masked || kase.no_gstin) && (
        <div className="kblock">
          <h3>{L("docsTitle")}</h3>
          <p className="hint" style={{ marginTop: 0 }}>{L("docsHint")}</p>
          {kase.required_docs.map((d) => (
            <DocSlot key={d} lang={lang} kase={kase} docType={d} busy={busy}
                     onUpload={(dt, f) => run(() => api.kycUpload(kase.id, dt, f), setKase)} />
          ))}
          <button className="btn btn-primary btn-block" disabled={busy || !docsReady}
                  onClick={() => run(() => api.kycEvaluate(kase.id), (c) => { setKase(c); if (c.outcome) onVerified(c.outcome); })}>
            {busy ? L("checking") : L("checkDocs")}
          </button>
        </div>
      )}

      {others.length > 0 && (
        <details className="kblock">
          <summary>{L("whatWeChecked")} ({others.length})</summary>
          <ul className="checklist">{others.map((c, i) => (
            <li key={i} className={`c-${c.status}`}>{c.status === "pass" ? <CircleCheck size={18} /> : <CircleAlert size={18} />}{c.message}</li>))}
          </ul>
        </details>
      )}

      <button className="linkbtn" disabled={busy}
              onClick={() => run(() => api.kycWithdraw(kase.id), (c) => { setKase(c); onToast(L("deleted")); })}>{L("deleteDocs")}</button>

      {samples.length > 0 && (
        <div className="demo">
          <h3>{L("demoTitle")}</h3>
          <p className="hint" style={{ marginTop: 0 }}>{L("demoSub")}</p>
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
    </section>
  );
}
