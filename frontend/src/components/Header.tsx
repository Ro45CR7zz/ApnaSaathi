import { Check, MessagesSquare, PhoneCall } from "lucide-react";
import type { Lang } from "../api";
import { t, tl } from "../i18n";

export function Brand({ sub }: { sub: string }) {
  return (
    <div className="brand">
      <span className="mark" aria-hidden="true"><MessagesSquare size={20} strokeWidth={2.2} /></span>
      <span className="brand-t"><b>apnaSaathi</b><span>{sub}</span></span>
    </div>
  );
}

export function Header({ lang, setLang, onCall }: { lang: Lang; setLang: (l: Lang) => void; onCall: () => void }) {
  return (
    <header className="topbar">
      <div className="topbar-in">
        <Brand sub={t(lang, "by")} />
        <div className="langswitch" role="group" aria-label="Language / भाषा">
          <button aria-pressed={lang === "hi"} onClick={() => setLang("hi")} lang="hi">हिन्दी</button>
          <button aria-pressed={lang === "en"} onClick={() => setLang("en")} lang="en">English</button>
        </div>
        <button className="callbtn" onClick={onCall} aria-label={t(lang, "callMe")}>
          <PhoneCall size={17} aria-hidden="true" /><span className="callbtn-text">{t(lang, "callMe")}</span>
        </button>
      </div>
    </header>
  );
}

export function Journey({ lang, step }: { lang: Lang; step: number }) {
  const names = tl(lang, "steps");
  return (
    <nav className="journey-wrap" aria-label={t(lang, "stepOf", { n: step })}>
      <ol className="journey">
        {names.map((name, i) => {
          const n = i + 1;
          const cls = n < step ? "done" : n === step ? "now" : "";
          return (
            <li key={name} className={cls} aria-current={n === step ? "step" : undefined}>
              <span className="dot">{n < step ? <Check size={15} strokeWidth={3} /> : n}</span>{name}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
