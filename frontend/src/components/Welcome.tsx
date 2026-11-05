import { Mic, Hand, ShieldCheck } from "lucide-react";
import type { Lang } from "../api";
import { t, tl } from "../i18n";
import { speechSupported } from "../speech";
import { Icon } from "./Icon";

const SAMPLE_ICONS = ["router", "smartphone", "qr-code", "cctv"];
const BAR_WIDTHS = [64, 52, 58, 46];

export function Welcome({ lang, onStart }: { lang: Lang; onStart: (voice: boolean) => void }) {
  const lines = tl(lang, "sampleLines");
  return (
    <section className="welcome">
      <div>
        <h1>{t(lang, "welcomeTitle")}</h1>
        <p className="lead">{t(lang, "welcomeSub")}</p>
        <div className="actions">
          {speechSupported() && (
            <button className="btn btn-primary btn-block" onClick={() => onStart(true)}>
              <Mic size={24} aria-hidden="true" />{t(lang, "startSpeak")}
            </button>
          )}
          <button className={`btn btn-block ${speechSupported() ? "btn-secondary" : "btn-primary"}`} onClick={() => onStart(false)}>
            <Hand size={22} aria-hidden="true" />{t(lang, "startTap")}
          </button>
        </div>
        <p className="fineprint"><ShieldCheck size={18} aria-hidden="true" />{t(lang, "privacyLine")}</p>
      </div>
      <figure className="stub" aria-label={t(lang, "sampleTitle")}>
        <h2>{t(lang, "sampleTitle")}</h2>
        {lines.map((l, i) => (
          <div className="r" key={l}>
            <Icon name={SAMPLE_ICONS[i]} size={22} /><span>{l}</span>
            <span className="bar" style={{ width: BAR_WIDTHS[i] }} />
          </div>
        ))}
        <div className="t"><span>{t(lang, "sampleTotal")}</span><span className="bar" /></div>
      </figure>
    </section>
  );
}
