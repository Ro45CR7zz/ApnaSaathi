import { useCallback, useEffect, useRef, useState } from "react";
import type { Lang } from "./api";

// Browser speech: recognition (Chrome/Edge, Android) and text-to-speech. Text input always works as fallback.
type Rec = {
  lang: string; interimResults: boolean; continuous: boolean; start(): void; stop(): void; abort(): void;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null;
};

function getRecognition(): (new () => Rec) | null {
  const w = window as unknown as Record<string, unknown>;
  return (w.SpeechRecognition || w.webkitSpeechRecognition || null) as (new () => Rec) | null;
}

export const speechSupported = () => typeof window !== "undefined" && getRecognition() !== null;

export function useListen(lang: Lang, onFinal: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const recRef = useRef<Rec | null>(null);
  const finalRef = useRef(onFinal);
  finalRef.current = onFinal;

  const stop = useCallback(() => { recRef.current?.stop(); }, []);

  const start = useCallback(() => {
    const R = getRecognition();
    if (!R) return false;
    window.speechSynthesis?.cancel();
    const rec = new R();
    rec.lang = lang === "hi" ? "hi-IN" : "en-IN";
    rec.interimResults = true;
    rec.continuous = false;
    let finalText = "";
    rec.onresult = (e) => {
      let text = "";
      for (let i = 0; i < e.results.length; i++) {
        const r = e.results[i];
        text += r[0].transcript;
        if (r.isFinal) finalText = text;
      }
      setInterim(text);
    };
    rec.onerror = () => setListening(false);
    rec.onend = () => {
      setListening(false);
      setInterim("");
      if (finalText.trim()) finalRef.current(finalText.trim());
    };
    recRef.current = rec;
    rec.start();
    setListening(true);
    return true;
  }, [lang]);

  useEffect(() => () => recRef.current?.abort(), []);
  return { listening, interim, start, stop };
}

export function speak(text: string, lang: Lang) {
  const synth = window.speechSynthesis;
  if (!synth) return;
  synth.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = lang === "hi" ? "hi-IN" : "en-IN";
  const voice = synth.getVoices().find((v) => v.lang.toLowerCase().startsWith(u.lang.toLowerCase()));
  if (voice) u.voice = voice;
  u.rate = 0.95;
  synth.speak(u);
}
