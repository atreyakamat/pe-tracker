import type { Zone } from "./stats";

export const ZONE_UI: Record<Zone, { label: string; icon: string; color: string; blurb: string }> = {
  BUY: { label: "Buy zone", icon: "▼", color: "var(--good)", blurb: "Cheap vs its own history. Add beyond your regular SIP." },
  NEUTRAL: { label: "Fair value", icon: "●", color: "var(--neutral-zone)", blurb: "Around its historical norm. Keep your regular SIP." },
  EXPENSIVE: { label: "Expensive", icon: "▲", color: "var(--critical)", blurb: "Rich vs history. Keep the SIP, skip extra lump sums." },
};

export const fmtDate = (d: string) =>
  new Date(d + "T00:00:00Z").toLocaleDateString("en-IN", { month: "short", year: "2-digit", timeZone: "UTC" });
export const fmtFull = (d: string) =>
  new Date(d + "T00:00:00Z").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
