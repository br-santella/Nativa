type Kind = "farm" | "crop" | "location" | "area";

const paths: Record<Kind, string> = {
  farm: "M3 10 12 3l9 7M5 9v12h14V9M9 21v-7h6v7",
  crop: "M12 21v-9M12 15C6 15 3 12 3 7c6 0 9 3 9 8ZM12 12c0-5 3-8 9-8 0 5-3 8-9 8Z",
  location: "M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0ZM15 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z",
  area: "M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5M8 16l8-8M11 8h5v5M8 11v5h5",
};

export default function PropertyIcon({ kind }: { kind: Kind }) {
  return <span className="property-summary-icon" aria-hidden="true">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={paths[kind]} /></svg>
  </span>;
}
