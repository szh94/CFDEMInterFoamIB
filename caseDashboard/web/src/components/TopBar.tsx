import { useMemo } from "react";
import { useStore } from "../store";
import { useLiveEdits, useT } from "../hooks";
import { FileMenu } from "./FileMenu";
import { IconDiff, IconGlobe, IconSpinner, IconTheme, IconUndo } from "./Icons";

/**
 * Fixed widths for the controls whose own text is not fixed, one entry per
 * language, content centred inside the box.
 *
 * Left to size themselves they shove their neighbours around: the level pill
 * flips between "Checks pass" and "12 warnings" while you type, and the style
 * button between "Default" and "Light".
 *
 * One width per language rather than one shared: the Chinese labels are much
 * shorter, and sizing both to the English maximum left 「回滚」 in a box with
 * 30px of dead space around it.
 *
 * Measured at 1560px -- widest state of each, EN / ZH: the pill 76.5 / 65.9,
 * Roll back 88.6 / 65, the style button 79.3 / 65.  Each box carries a few px
 * of slack; a label that does not fit would wrap and burst the 32px row.
 */
const W_LEVEL_PILL = { en: "w-[5rem]", zh: "w-[4.4rem]" };
const W_ROLL_BACK = { en: "w-[6rem]", zh: "w-[4.4rem]" };
const W_THEME = { en: "w-[5.2rem]", zh: "w-[4.4rem]" };

export function TopBar() {
  const payload = useStore((s) => s.payload);
  const busy = useStore((s) => s.busy);
  const loading = useStore((s) => s.loading);
  const derived = useStore((s) => s.derived);
  const lang = useStore((s) => s.lang);
  const setLang = useStore((s) => s.setLang);
  const theme = useStore((s) => s.theme);
  const setTheme = useStore((s) => s.setTheme);
  const openDiff = useStore((s) => s.openDiff);
  const requestRevert = useStore((s) => s.requestRevert);
  const resetAll = useStore((s) => s.resetAll);
  const liveEdits = useLiveEdits();
  const t = useT();

  const dirtyCount = liveEdits.length;
  const summary = derived?.summary;

  const levelPill = useMemo(() => {
    if (!summary) return null;
    if (summary.errors > 0)
      return { cls: "border-error/40 bg-error/10 text-error", text: t.t("{n} errors", { n: summary.errors }) };
    if (summary.warnings > 0)
      return { cls: "border-warn/40 bg-warn/10 text-warn", text: t.t("{n} warnings", { n: summary.warnings }) };
    return { cls: "border-ok/30 bg-ok/10 text-ok", text: t.t("Checks pass") };
  }, [summary, t]);

  return (
    <header className="glass-bar z-20 flex h-14 shrink-0 items-center gap-3 border-b border-line px-4">
      {/* No brand block: the window title already reads "CFDEMInterFoamIB · Case
          dashboard" (`store.setLang` writes it), and in the application window
          the title bar shows it a few pixels above this row. */}

      {/* A single `h-8` across the row rather than `items-stretch`: the case
          chip carries two lines and would otherwise set the cross size, making
          the File menu taller than the action buttons. */}
      <div className="flex items-center gap-3">
        <FileMenu />

        {levelPill && (
          <span
            className={`flex h-8 ${W_LEVEL_PILL[lang]} shrink-0 items-center justify-center rounded border px-2 text-[11px] ${levelPill.cls}`}
          >
            {levelPill.text}
          </span>
        )}

        <button
          onClick={resetAll}
          disabled={!dirtyCount || busy}
          className="btn-glass flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2.5 text-[12px] text-ink-2 transition hover:text-ink disabled:opacity-35"
          title={t.t("Discard every unwritten change")}
        >
          <IconUndo width={13} height={13} />
          {t.t("Cancel changes")}
        </button>

        <button
          onClick={openDiff}
          disabled={!dirtyCount || busy}
          className="btn-gloss flex h-8 shrink-0 items-center gap-1.5 rounded-md bg-accent px-3 text-[12px] font-medium text-accent-ink disabled:opacity-35"
          title={t.t("Preview the diff and write the files")}
        >
          {busy ? <IconSpinner width={13} height={13} /> : <IconDiff width={13} height={13} />}
          {t.t("Apply changes")}
        </button>
      </div>

      {dirtyCount > 0 && (
        <span className="rounded border border-dirty/40 bg-dirty/10 px-2 py-1 text-[11px] text-dirty">
          {t.t("{n} unwritten", { n: dirtyCount })}
        </span>
      )}

      <div className="flex-1" />

      {loading && <IconSpinner width={14} height={14} className="text-ink-3" />}

      <button
        onClick={requestRevert}
        disabled={busy || !payload}
        className={`btn-glass flex h-8 ${W_ROLL_BACK[lang]} shrink-0 items-center justify-center gap-1.5 rounded-md px-2.5 text-[12px] text-ink-2 transition hover:text-ink disabled:opacity-35`}
        title={t.t("Restore the files from the last snapshot")}
      >
        <IconUndo width={13} height={13} />
        {t.t("Roll back")}
      </button>

      <button
        onClick={() => void setLang(lang === "zh" ? "en" : "zh")}
        className="btn-glass flex h-8 items-center gap-1.5 rounded-md px-2.5 text-[12px] text-ink-2 transition hover:text-ink"
        title={t.t(lang === "zh" ? "Switch to English" : "Switch to Chinese")}
      >
        <IconGlobe width={13} height={13} />
        {/* The language the panel is in, not the one the click would switch to. */}
        {lang === "zh" ? "中" : "EN"}
      </button>

      {/* Alongside the language button because it is the same kind of control:
          a display preference that costs no request.  Like the language chip it
          names the style the panel is in, not the one the click would move to. */}
      <button
        onClick={() => void setTheme(theme === "light" ? "default" : "light")}
        className={`btn-glass flex h-8 ${W_THEME[lang]} shrink-0 items-center justify-center gap-1.5 rounded-md px-2.5 text-[12px] text-ink-2 transition hover:text-ink`}
        title={t.t(
          theme === "light" ? "Switch to the default style" : "Switch to the light style",
        )}
      >
        <IconTheme width={13} height={13} />
        {t.t(theme === "light" ? "Light" : "Default")}
      </button>
    </header>
  );
}
