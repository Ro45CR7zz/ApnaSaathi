import { PhoneCall } from "lucide-react";
import type { Lang } from "../api";
import { t, tl } from "../i18n";

export function Header({ lang, setLang, onCall }: { lang: Lang; setLang: (l: Lang) => void; onCall: () => void }) {
  return (
    <header className="topbar">
      <div className="wordmark"><b>apnaSaathi</b><span>{t(lang, "by")}</span></div>
      <div className="langswitch" role="group" aria-label="Language / भाषा">
        <button aria-pressed={lang === "hi"} onClick={() => setLang("hi")} lang="hi">हिन्दी</button>
        <button aria-pressed={lang === "en"} onClick={() => setLang("en")} lang="en">English</button>
      </div>
      <button className="callbtn" onClick={onCall} aria-label={t(lang, "callMe")}>
        <PhoneCall size={18} aria-hidden="true" /><span className="callbtn-text">{t(lang, "callMe")}</span>
      </button>
    </header>
  );
}

export function Journey({ lang, step }: { lang: Lang; step: number }) {
  const names = tl(lang, "steps");
  return (
    <nav aria-label={t(lang, "stepOf", { n: step })}>
      <ol className="journey">
        {names.map((name, i) => {
          const n = i + 1;
          const cls = n < step ? "done" : n === step ? "now" : "";
          return (
            <li key={name} className={cls} aria-current={n === step ? "step" : undefined}>
              <span className="dot">{n < step ? "✓" : n}</span>{name}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
