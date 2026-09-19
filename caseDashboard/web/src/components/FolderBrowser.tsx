import { useEffect, useState } from "react";
import { api } from "../api";
import { useT } from "../hooks";
import { IconArrowUp, IconCheck, IconCross, IconFolder, IconSpinner } from "./Icons";
import type { BrowseListing } from "../types";

interface Props {
  /** Repository-relative path handed back; the caller opens it as a case. */
  onPick: (path: string) => void;
  onClose: () => void;
}

/**
 * The folder picker, drawn in the page rather than handed to the OS.
 *
 * The OS dialog it replaces could not be trusted to be *visible*: it is shown by
 * a process the browser spawned only indirectly, and Windows only lets the
 * foreground process (or one it started) raise a window -- so it opened behind
 * the browser, and neither an owner form nor a topmost flag could talk the
 * system out of that.  A picker inside the page has no such problem: it is drawn
 * by the window the user is already looking at.  It also stops the dashboard
 * from starting a process at all, which is one less thing it does.
 *
 * Navigation is one directory at a time -- the listing endpoint returns a single
 * level -- so the walk can also leave the repository, which it has to be able to:
 * a case is a directory with a ``CFD/system/controlDict``, and nothing says it
 * was cloned next to this dashboard.  The path line turns amber once the trail is
 * outside, so leaving is visible rather than silent.
 */
export function FolderBrowser({ onPick, onClose }: Props) {
  const t = useT();
  const [listing, setListing] = useState<BrowseListing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function go(path: string) {
    setBusy(true);
    try {
      setListing(await api.browse(path));
      setError(null);
    } catch (exc) {
      // The level stays on screen: a refused path should not blank the dialog,
      // only say why it was refused so another row can be tried.
      setError((exc as Error).message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void go("");
    // Only on mount: `go` is re-created every render and would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  /** The backend walks the tree anyway, so it hands back the trail -- which
      spares this component every Windows special case (a drive letter is a
      level, but `D:` is not a path; a filesystem root has no name). */
  const crumbs = listing?.crumbs ?? [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-base/75 backdrop-blur-sm" onClick={onClose} />

      <div className="anim-in glass-strong relative flex max-h-[80vh] w-full max-w-xl flex-col overflow-hidden rounded-xl">
        <div className="flex shrink-0 items-center gap-2 border-b border-line px-3.5 py-2.5">
          <IconFolder width={14} height={14} className="shrink-0 text-accent" />
          <h2 className="flex-1 text-[13px] font-medium">{t.t("Select the case folder")}</h2>
          <button
            onClick={onClose}
            title={t.t("Close")}
            className="btn-glass grid h-6 w-6 place-items-center rounded text-ink-3 transition hover:text-ink"
          >
            <IconCross width={12} height={12} />
          </button>
        </div>

        {/* Breadcrumb.  The repository is the first crumb while you are in it,
            so every level is one click away; once the walk has left it the trail
            starts at the drive instead and the repository is not an ancestor any
            more, which is why it is then offered separately. */}
        <div className="flex shrink-0 flex-wrap items-center gap-1 px-3.5 py-2 text-[11.5px]">
          {listing && !listing.inside_repo && (
            <>
              <button
                onClick={() => void go("")}
                className="rounded px-1 py-0.5 text-ink-3 transition hover:bg-panel-3"
              >
                {t.t("Repository")}
              </button>
              <span className="text-ink-4">›</span>
            </>
          )}
          {crumbs.map((c, i) => (
            <span key={c.path} className="flex items-center gap-1">
              {i > 0 && <span className="text-ink-4">›</span>}
              <button
                onClick={() => void go(c.path)}
                className={`max-w-[14rem] truncate rounded px-1 py-0.5 transition hover:bg-panel-3 ${
                  i === crumbs.length - 1 ? "font-medium text-ink" : "text-ink-3"
                }`}
              >
                {c.label}
              </button>
            </span>
          ))}
        </div>

        <div className="flex min-h-0 flex-1 flex-col border-y border-line">
          <button
            onClick={() => listing?.parent != null && void go(listing.parent)}
            disabled={listing?.parent == null || busy}
            className="flex shrink-0 items-center gap-2 px-3.5 py-2 text-left text-[12px] text-ink-2 transition enabled:hover:bg-panel-3 disabled:opacity-35"
          >
            <IconArrowUp width={13} height={13} />
            {t.t("Up one level")}
          </button>

          <div className="min-h-[10rem] flex-1 overflow-y-auto pb-1">
            {listing?.entries.map((e) => (
              <button
                key={e.path}
                onClick={() => void go(e.path)}
                className="flex w-full items-center gap-2 px-3.5 py-1.5 text-left transition hover:bg-panel-3"
              >
                <IconFolder
                  width={13}
                  height={13}
                  className={`shrink-0 ${e.is_case ? "text-accent" : "text-ink-4"}`}
                />
                <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-ink">
                  {e.name}
                </span>
                {/* Only the directories that can actually be opened are marked;
                    a marker on every row would say nothing. */}
                {e.is_case && (
                  <span className="flex shrink-0 items-center gap-1 rounded bg-accent/15 px-1.5 py-0.5 text-[10px] text-accent">
                    <IconCheck width={9} height={9} />
                    {t.t("Case")}
                  </span>
                )}
              </button>
            ))}

            {listing && !listing.entries.length && (
              <p className="px-3.5 py-2 text-[11.5px] text-ink-3">{t.t("No subfolders here.")}</p>
            )}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2 px-3.5 py-3">
          <span
            className={`min-w-0 flex-1 truncate font-mono text-[11px] ${
              listing && !listing.inside_repo ? "text-warn" : "text-ink-3"
            }`}
            title={listing?.path}
          >
            {busy && <IconSpinner width={11} height={11} className="mr-1 inline align-[-1px]" />}
            {listing ? listing.path || t.t("Repository root") : ""}
          </span>

          {error && (
            <span className="min-w-0 max-w-[18rem] truncate text-[11px] text-error" title={error}>
              {error}
            </span>
          )}
          {!error && listing && !listing.is_case && (
            <span className="shrink-0 text-[10.5px] text-ink-4">
              {t.t("Not a case (needs CFD/system/controlDict)")}
            </span>
          )}

          <button
            onClick={onClose}
            className="btn-glass shrink-0 rounded-md px-3 py-1.5 text-[12px] text-ink-2 transition"
          >
            {t.t("Cancel")}
          </button>
          <button
            onClick={() => listing && onPick(listing.path)}
            disabled={!listing?.is_case || busy}
            className="btn-gloss shrink-0 rounded-md bg-accent px-3.5 py-1.5 text-[12px] font-medium text-accent-ink disabled:opacity-35"
          >
            {t.t("Select this folder")}
          </button>
        </div>
      </div>
    </div>
  );
}
