// Badges that sum up what an option's second crop does for the soil, used on the option cards and in the scenario window.
import type { ItemRanking } from "./api";
import { CROP_ROLES, SOIL_ROLES, bareSoilDays } from "./cropRoles";

export default function SoilBadges({ item, baseline, en }: {
  item: ItemRanking;
  /** Today's rotation, for the bare-soil comparison (null when `item` is today's rotation). */
  baseline: ItemRanking | null;
  en: boolean;
}) {
  const say = (pt: string, english: string) => (en ? english : pt);
  const roles = item.segunda ? CROP_ROLES[item.segunda.id] ?? [] : [];
  const days = bareSoilDays(item.card?.evidencias);
  const daysToday = baseline ? bareSoilDays(baseline.card?.evidencias) : null;
  if (!roles.length && days == null) return null;
  return <div className="sd-badges soil-badges">
   {roles.map(({ role, scored }) => <span key={role} className={"sd-badge sd-role" + (scored ? " is-scored" : " is-info")}
     title={(en ? SOIL_ROLES[role].hint.en : SOIL_ROLES[role].hint.pt) + (scored ? "" : say(" Efeito conhecido, não calculado na nota.", " Known effect, not computed in the score."))}>
     {en ? SOIL_ROLES[role].label.en : SOIL_ROLES[role].label.pt}</span>)}
   {days != null && <span className="sd-badge" title={say("Dias por ano sem cultura no campo (catálogo do motor).", "Days per year with no crop in the field (engine catalog).")}>
    {say(`~${days} dias de solo descoberto`, `~${days} bare-soil days`)}
    {daysToday != null && daysToday !== days && <b className={days < daysToday ? "is-up" : "is-down"}>{say(` · hoje ~${daysToday}`, ` · today ~${daysToday}`)}</b>}
   </span>}
  </div>;
}
