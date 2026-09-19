import { useEffect, useRef, useState } from "react";
import { useStore } from "../store";
import { useT } from "../hooks";
import { FolderBrowser } from "./FolderBrowser";
import { IconChevron, IconFolderPlus, IconSpinner } from "./Icons";

/**
 * Case switching that does not depend on discovery.
 *
 * The case chip next to it only becomes clickable once `/api/cases` has found
 * more than one match, so with a single tutorial it is inert.  This menu always
 * opens and additionally takes a path by hand -- which is the only way to reach
 * a case buried deeper than the scan depth, or one that is not in the repository
 * at all.
 *
 * It cannot widen *what* is openable: the backend still insists on a directory
 * holding `CFD/system/controlDict`, wherever that directory happens to sit.  A
 * rejected path is reported by the store's toast.  Nothing has to match a name --
 * a case the parameter rules were not written for opens anyway and reports the
 * rules it could not locate.
 */
export function OpenProject() {
  const cases = useStore((s) => s.cases);
  const repo = useStore((s) => s.repo);
  const casePath = useStore((s) => s.casePath);
  const loading = useStore((s) => s.loading);
  const busy = useStore((s) => s.busy);
  const selectCase = useStore((s) => s.selectCase);
  const [open, setOpen] = useState(false);
  const [path, setPath] = useState("");
  const [browsing, setBrowsing] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const t = useT();

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Reopening should start from an empty box, not the path that failed last time.
  useEffect(() => {
    if (open) setPath("");
  }, [open]);

  const disabled = loading || busy;

  async function openTarget(target: string) {
    const trimmed = target.trim();
    if (!trimmed || disabled) return;
    // The store owns the error reporting; close only once it actually landed,
    // so a typo leaves the menu (and the box) in place to be corrected.
    if (await selectCase(trimmed)) setOpen(false);
  }

  /**
   * The in-page folder browser, which hands back a path the same way a typed one
   * arrives -- so a folder it offers but the case rules reject is still reported
   * by the one place that owns those rules, and still sits in the box to be
   * corrected.
   */
  async function picked(target: string) {
    setBrowsing(false);
    setOpen(false);
    setPath(target);
    await openTarget(target);
  }

  return (
    <div ref={ref} className="relative self-center">
      <button
        onClick={() => setOpen((v) => !v)}
        className="btn-glass flex h-8 items-center gap-1.5 rounded-md px-2.5 text-[12px] text-ink-2 transition hover:text-ink"
        title={t.t("Switch to another case folder")}
      >
        <IconFolderPlus width={13} height={13} className="text-accent" />
        {t.t("Open project")}
        <IconChevron
          width={12}
          height={12}
          className={`transition ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="anim-in glass-strong absolute left-0 top-full z-40 mt-2 w-[24rem] overflow-hidden rounded-lg">
          <p className="px-3 pb-1 pt-2.5 text-[10.5px] text-ink-3">
            {t.t("Cases found by the scan")}
          </p>

          {cases.length ? (
            cases.map((c) => (
              <button
                key={c.path}
                onClick={() => {
                  if (c.path === casePath) return setOpen(false);
                  void openTarget(c.path);
                }}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left transition hover:bg-panel-3 ${
                  c.path === casePath ? "bg-accent/10" : ""
                }`}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12.5px] text-ink">{c.path}</span>
                  <span className="block truncate text-[10.5px] text-ink-3">
                    {t.t("{a}/{b} parameters recognized", { a: c.recognized, b: c.total })}
                  </span>
                </span>
                {c.path === casePath && (
                  <span className="shrink-0 rounded bg-accent/20 px-1.5 py-0.5 text-[10px] text-accent">
                    {t.t("Current")}
                  </span>
                )}
              </button>
            ))
          ) : (
            <p className="px-3 py-2 text-[11.5px] text-ink-3">{t.t("No cases were found.")}</p>
          )}

          <div className="my-1 h-px bg-line" />

          <div className="px-3 pb-3 pt-1.5">
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <p className="text-[10.5px] text-ink-3">{t.t("Or type a path")}</p>
              <button
                onClick={() => setBrowsing(true)}
                disabled={disabled}
                title={t.t("Browse folders in the page")}
                className="btn-glass flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[10.5px] text-ink-3 transition hover:text-ink disabled:opacity-40"
              >
                <IconFolderPlus width={10} height={10} />
                {t.t("Browse…")}
              </button>
            </div>
            <div className="flex items-center gap-2">
              <input
                autoFocus
                value={path}
                onChange={(e) => setPath(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void openTarget(path);
                }}
                placeholder="tutorial/single_sphere"
                spellCheck={false}
                disabled={disabled}
                className="min-w-0 flex-1 rounded border border-line bg-field px-2 py-1.5 font-mono text-[11.5px] text-ink outline-none transition placeholder:text-ink-3 focus:border-accent/60 disabled:opacity-50"
              />
              <button
                onClick={() => void openTarget(path)}
                disabled={!path.trim() || disabled}
                className="btn-gloss flex shrink-0 items-center gap-1 rounded bg-accent px-2.5 py-1.5 text-[11.5px] font-medium text-accent-ink disabled:opacity-35"
              >
                {loading && <IconSpinner width={12} height={12} />}
                {t.t("Check and open")}
              </button>
            </div>
            <p className="mt-1.5 truncate font-mono text-[10px] text-ink-3" title={repo}>
              {t.t("Relative to {repo}", { repo })}
            </p>
          </div>
        </div>
      )}

      {browsing && (
        <FolderBrowser onClose={() => setBrowsing(false)} onPick={(p) => void picked(p)} />
      )}
    </div>
  );
}
