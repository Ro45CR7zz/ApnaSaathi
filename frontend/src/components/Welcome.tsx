import { ArrowRight, AudioLines, Check, Mic } from "lucide-react";
import type { Lang } from "../api";
import { inr } from "../api";
import { t, tl } from "../i18n";
import { speechSupported } from "../speech";
import { BUSINESS } from "./Advisor";
import { Icon } from "./Icon";

// A real output of the pricing engine (kirana store, Jaipur, 3 people, UPI billing + CCTV), shown as an example.
const EXAMPLE = [
  { icon: "router", amt: 1074, was: 1099 },
  { icon: "cctv", amt: 473, was: 498 },
  { icon: "qr-code", amt: 711, was: 749 },
];

export function Welcome({ lang, onStart }: { lang: Lang; onStart: (voice: boolean, biz?: { value: string; label: string }) => void }) {
  const names = tl(lang, "exampleLines");
  const L = (b: { en: string; hi: string }) => (lang === "hi" ? b.hi : b.en);
  return (
    <section className="welcome">
      <div>
        <h1>{t(lang, "welcomeTitle")}</h1>
        <p className="lead">{t(lang, "welcomeSub")}</p>

        {speechSupported() && (
          <div className="card voicecard">
            <span className="vc-ic"><AudioLines size={26} aria-hidden="true" /></span>
            <span className="vc-t"><b>{t(lang, "voiceTitle")}</b><span>{t(lang, "voiceSub")}</span></span>
            <button className="btn btn-primary btn-lg" onClick={() => onStart(true)}>
              <Mic size={20} aria-hidden="true" />{t(lang, "startSpeak")}
            </button>
          </div>
        )}

        <div className="biz-head"><h2>{t(lang, "pickBusiness")}</h2><span>{t(lang, "pickBusinessSub")}</span></div>
        <div className="biz-grid">
          {BUSINESS.map((b) => (
            <button key={b.value} className="biz" onClick={() => onStart(false, { value: b.value, label: L(b) })}>
              <span className="ic"><Icon name={b.icon} size={20} /></span>{L(b)}
            </button>
          ))}
        </div>
        <button className="other" onClick={() => onStart(false)}>
          {t(lang, "otherStart")}<span className="go"><ArrowRight size={18} aria-hidden="true" /></span>
        </button>
      </div>

      <aside>
        <figure className="bill" aria-label={t(lang, "exampleTitle")} style={{ margin: 0 }}>
          <div className="bill-top"><h2 style={{ fontSize: 22 }}>{t(lang, "exampleTitle")}</h2><span className="pill">{t(lang, "example")}</span></div>
          <p className="who">{t(lang, "exampleWho")}</p>
          {EXAMPLE.map((e, i) => (
            <div className="line" key={e.icon}>
              <span className="ic"><Icon name={e.icon} size={20} /></span>
              <span className="nm">{names[i]}</span>
              <span className="amt">{inr(e.amt)}</span>
              <span />
              <span className="was">{inr(e.was)}</span>
            </div>
          ))}
          <div className="total">
            <div className="big"><span>{t(lang, "everyMonth")}</span><b>{inr(2664)}</b></div>
            <div className="sub"><span>{t(lang, "inclGst", { sub: inr(2258), gst: inr(406) })}</span></div>
          </div>
        </figure>
        <ul className="promise">
          {tl(lang, "promises").map((p) => <li key={p}><Check size={16} strokeWidth={2.6} aria-hidden="true" />{p}</li>)}
        </ul>
      </aside>
    </section>
  );
}
