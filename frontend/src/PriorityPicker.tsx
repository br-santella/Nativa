// Priority profiles plus the engine's five criteria (0–10), shared by Rotation Strategies and Settings
// so both edit the same weights with the same controls as the setup wizard.
import { useState } from "react";
import type { Pesos } from "./api";
import { useLanguage } from "./i18n";
import { CRITERIA, PRIORITIES, matchPriority } from "./priorities";
import type { PriorityId } from "./priorities";
import "./rotation-strategies.css";

export default function PriorityPicker({ pesos, onChange }: { pesos: Pesos; onChange: (pesos: Pesos) => void }) {
  const { language } = useLanguage();
  const en = language === "en";
  const say = (pt: string, english: string) => (en ? english : pt);
  const tx = (text: { pt: string; en: string }) => (en ? text.en : text.pt);
  // Manual edits stay "custom" even if they happen to match a profile.
  const [custom, setCustom] = useState(() => matchPriority(pesos) === "custom");
  const selected: PriorityId | "custom" = custom ? "custom" : matchPriority(pesos);
  const choose = (id: PriorityId) => { setCustom(false); onChange({ ...PRIORITIES.find((p) => p.id === id)!.pesos }); };
  const setWeight = (id: keyof Pesos, value: number) => { setCustom(true); onChange({ ...pesos, [id]: value }); };
  return (<div className="rs-priority-picker">
    <div className="rs-profiles">
      {PRIORITIES.map((p) => (<button key={p.id} type="button" className={"rs-profile" + (selected === p.id ? " is-selected" : "")} aria-pressed={selected === p.id} onClick={() => choose(p.id)}>
          <span className="rs-profile-icon" aria-hidden="true">{p.icon}</span><span><strong>{tx(p.title)}</strong><small>{tx(p.description)}</small></span>
        </button>))}
    </div>
    <details className="rs-adjust" open={selected === "custom"}>
      <summary>{selected === "custom" ? say("Ajuste do seu jeito · em uso", "Your own balance · in use") : say("Ajuste do seu jeito", "Make it your own")}</summary>
      <div className="rs-sliders">
        {CRITERIA.map((c) => (<label key={c.id} className="rs-slider">
            <span><strong>{tx(c.name)}</strong><output>{pesos[c.id]}<small>/10</small></output></span>
            <input type="range" min="0" max="10" value={pesos[c.id]} onChange={(e) => setWeight(c.id, Number(e.target.value))}/>
            <small>{tx(c.hint)}</small>
          </label>))}
      </div>
    </details>
  </div>);
}
