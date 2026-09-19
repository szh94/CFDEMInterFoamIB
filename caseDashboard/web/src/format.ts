import type { Translator } from "./i18n";
import type { Level, Recognition } from "./types";

/**
 * Compact rendering for the dense grid: 6 significant digits, exponential only
 * outside a comfortable fixed-notation band.
 *
 * This is a *display* formatter -- it rounds, e.g. 2.2222222222e-3 -> "0.00222222".
 * Inputs must therefore never commit a value the user did not retype; see
 * `NumberBox`, which compares against the text it seeded the field with.
 */
export function fmtNum(n: number): string {
  if (!Number.isFinite(n)) return String(n);
  if (n === 0) return "0";
  const abs = Math.abs(n);
  if (abs >= 1e7 || abs < 1e-4) return n.toExponential(4);
  return String(Number(n.toPrecision(6)));
}

export const LEVEL_STYLE: Record<
  Level,
  { dot: string; text: string; bg: string; ring: string }
> = {
  ok: { dot: "bg-ok", text: "text-ok", bg: "bg-ok/10", ring: "ring-ok/30" },
  info: { dot: "bg-info", text: "text-info", bg: "bg-info/10", ring: "ring-info/30" },
  warn: { dot: "bg-warn", text: "text-warn", bg: "bg-warn/10", ring: "ring-warn/30" },
  error: { dot: "bg-error", text: "text-error", bg: "bg-error/10", ring: "ring-error/30" },
};

/**
 * Severity order, worst first -- the one ranking every sort in the panel uses.
 *
 * Typed as a `Record<Level, …>` on purpose: adding a member to `Level` then
 * fails to compile here, rather than sorting the new level as `undefined` and
 * quietly putting it wherever it happened to sit.
 */
export const LEVEL_RANK: Record<Level, number> = { error: 0, warn: 1, info: 2, ok: 3 };

/** `CFD/system/blockMeshDict` -> `system/blockMeshDict` (drop the case root). */
export function shortenFile(file: string): string {
  const parts = file.split("/");
  return parts.length > 2 ? parts.slice(1).join("/") : file;
}

/**
 * One line saying how much of the parameter list this case matched.
 *
 * There is no per-case profile to name any more -- the same rules are applied
 * everywhere -- so what identifies an open case is how much of them landed.
 */
export function recognitionLine(rec: Recognition, t: Translator): string {
  const vars = { a: rec.recognized, b: rec.total };
  if (rec.unrecognized.length === 0) {
    return t.t("All {n} parameters recognized", { n: rec.total });
  }
  return t.t("{a}/{b} parameters recognized", vars);
}
