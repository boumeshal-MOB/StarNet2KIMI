export function fmtCoord(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtMm(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return (value * 1000).toFixed(digits);
}

export function fmtEpoch(iso: string | null | undefined): string {
  if (!iso) return "—";
  return iso.replace("T", " ").replace(".000Z", "Z").replace("Z", " UTC");
}

export function fmtSlot(iso: string | null | undefined): string {
  if (!iso) return "—";
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)}`;
}

export function fmtDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}
