import { useEffect, useState } from "react";
import { useStore } from "./store";
import { useLiveEdits, useT } from "./hooks";
import { shortenFile } from "./format";
import { TabBar } from "./components/TabBar";
import { TopBar } from "./components/TopBar";
import { ParamPanel } from "./components/ParamPanel";
import { StepsPanel } from "./components/StepsPanel";
import { DerivedPanel } from "./components/DerivedPanel";
import { GeometryView } from "./components/GeometryView";
import { DiffDrawer } from "./components/DiffDrawer";
import { FileEditor } from "./components/FileEditor";
import { Toasts } from "./components/Toast";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { IconChevron, IconSpinner } from "./components/Icons";
import type { Group } from "./types";

/**
 * The geometry page is the dashboard's own, not the case's: it holds no
 * parameter and is put in front of the backend's groups here, so a case's own
 * tab list is never touched by it.  Written in the same shape a group has, so
 * the tab bar needs to know nothing about the difference.
 */
const GEOMETRY: Group = {
  id: "geometry",
  label: "Geometry inspection",
  blurb: "",
  kind: "geometry",
  param_ids: [],
};

const GROUP_HINT: Record<string, string> = {
  geometry:
    "Geometry inspection: the corners, boundary faces and particles the rules read, drawn from the same effective values the metrics compute with. A face is coloured by its patch and carries an arrow along the normal its own corner order gives, so a face wound the wrong way points into the box. The same picture sits small in the sidebar, where it stays put while the tabs move.",
  fluid:
    "Fluid side: mesh size, physical properties (viscosity, density, surface tension, turbulence and gravity), initial water level, parallel decomposition and solver controls. The same quantity is defined in several files, and the panel on the right flags mismatches as you type.",
  particle:
    "Particle side: LIGGGHTS particle properties, the DEM region and the coupling frequency. Wall coordinates get their own card and must match the fluid domain boundary face by face.",
  coupling:
    "Coupling side: the coupling interval is typed here and written into the DEM deck's couple_every when you apply, so the particle tab shows that copy read-only and follows this one as you type.",
  steps:
    "Run steps: every step*.sh in the case folder, each against what it has already produced on disk. This page only reads the directory -- nothing here runs a script -- so re-check after running a step in WSL.",
};

export default function App() {
  const boot = useStore((s) => s.boot);
  const payload = useStore((s) => s.payload);
  const loading = useStore((s) => s.loading);
  const busy = useStore((s) => s.busy);
  const revert = useStore((s) => s.revert);
  const revertConfirm = useStore((s) => s.revertConfirm);
  const cancelRevert = useStore((s) => s.cancelRevert);
  const focusParam = useStore((s) => s.focusParam);
  const focusSeq = useStore((s) => s.focusSeq);
  const loadScripts = useStore((s) => s.loadScripts);
  // The picture first: a case opens on what it is, and the field pages are one
  // click behind it.
  const [active, setActive] = useState(GEOMETRY.id);
  const [sidebar, setSidebar] = useState(true);
  const t = useT();

  useEffect(() => {
    void boot();
  }, [boot]);

  const groups = payload?.groups ?? [];
  /** What the tab bar shows: our geometry page, then whatever the case sent. */
  const tabs = payload ? [GEOMETRY, ...groups] : [];
  const group = tabs.find((g) => g.id === active);

  useEffect(() => {
    // Against `tabs`, not `groups`: the geometry page is ours, so a case whose
    // group list changes under it must not throw the user back to the fluid
    // page.  A tab that really went away still falls back to the first of the
    // case's own, never to the geometry page, which is always there.
    if (groups.length && !tabs.some((g) => g.id === active)) {
      setActive(groups[0].id);
    }
  }, [groups, tabs, active]);

  /**
   * The script page answers from the directory, not from the payload, so it has
   * to ask again every time it is opened -- a script run in WSL in the meantime
   * changes nothing the dashboard would otherwise notice.
   *
   * Keyed on `active` rather than on the tab click, because two other things
   * move the tab without one: the focus jump below, and the reset when a case
   * changes its group list.
   */
  useEffect(() => {
    if (active === "steps") void loadScripts();
  }, [active, loadScripts]);

  /**
   * A click in the derived panel asks for a field that may live on another tab, so
   * the tab follows the request.  Keyed on the counter rather than on
   * `focusParam`, so re-clicking a source already in focus still jumps -- while
   * a manual tab switch, or the payload a write replaces, does not pull back.
   */
  useEffect(() => {
    if (!focusSeq || !payload) return;
    const target = payload.params.find((p) => p.id === focusParam);
    if (target) setActive(target.group);
  }, [focusSeq]);

  return (
    <div className="ambient flex h-full flex-col bg-base">
      <TopBar />

      {payload && (
        <TabBar groups={tabs} active={active} onChange={setActive} />
      )}

      <div className="flex min-h-0 flex-1">
        <main className="min-w-0 flex-1 overflow-y-auto px-4 py-4">
          {!payload ? (
            <Placeholder loading={loading} />
          ) : (
            <div className="mx-auto max-w-6xl space-y-3">
              <RecognitionNotice />
              <p className="text-[11.5px] leading-relaxed text-ink-3">
                {t.t(GROUP_HINT[active] ?? "")}
              </p>
              {group?.kind === "geometry" ? (
                // The page is the card: full width of the column, and taller
                // than the sidebar's copy of it, which is the point of having
                // the two.
                <GeometryView stage />
              ) : group?.kind === "scripts" ? (
                <StepsPanel />
              ) : (
                <ParamPanel groupId={active} />
              )}
            </div>
          )}
        </main>

        {/* ---- derived sidebar ---- */}
        <aside
          className={`relative shrink-0 border-l border-line bg-wash/50 transition-[width] duration-200 ${
            sidebar ? "w-[21rem]" : "w-9"
          }`}
        >
          <button
            onClick={() => setSidebar((v) => !v)}
            className="absolute -left-9 top-3 z-10 grid h-6 w-6 place-items-center rounded-full border-2 border-accent/60 bg-accent/25 text-accent shadow-lg backdrop-blur-md transition hover:border-accent hover:bg-accent hover:text-accent-ink active:scale-95"
            title={t.t(sidebar ? "Collapse the derived panel" : "Expand the derived panel")}
          >
            <IconChevron
              width={14}
              height={14}
              strokeWidth={2}
              className={`transition ${sidebar ? "rotate-90" : "-rotate-90"}`}
            />
          </button>

          {sidebar ? (
            // Two cards, not a card within one: the geometry picture is its own
            // answer about the case, so it stands beside the metrics panel
            // rather than under its heading.
            <div className="flex h-full flex-col gap-2 p-2">
              <GeometryView />
              <DerivedPanel />
            </div>
          ) : (
            <div className="flex h-full items-center justify-center">
              <span className="whitespace-nowrap text-[10.5px] text-ink-4 [writing-mode:vertical-rl]">
                {t.t("Derived metrics and checks")}
              </span>
            </div>
          )}
        </aside>
      </div>

      <StatusBar busy={busy} />

      <DiffDrawer />
      <FileEditor />
      <Toasts />

      <ConfirmDialog
        open={revertConfirm}
        danger
        title={t.t("Roll back to the previous snapshot?")}
        body={t.t(
          "This overwrites the current files with the original bytes from the snapshot.\nUnwritten changes are lost as well.",
        )}
        confirmLabel={t.t("Roll back")}
        onCancel={cancelRevert}
        onConfirm={() => void revert()}
      />
    </div>
  );
}

function Placeholder({ loading }: { loading: boolean }) {
  const t = useT();
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-ink-3">
      {loading ? (
        <>
          <IconSpinner width={20} height={20} className="text-accent" />
          <p className="text-[12.5px]">{t.t("Reading the case…")}</p>
        </>
      ) : (
        <>
          <p className="text-[12.5px]">{t.t("No usable case was found.")}</p>
          <p className="max-w-md text-center text-[11px] leading-relaxed text-ink-4">
            {t.t("A case needs a")} <code className="font-mono">CFD/system/controlDict</code>
            {t.t(
              ", anywhere on disk. If nothing here matches, browse to one or type its path under File in the top bar.",
            )}
          </p>
        </>
      )}
    </div>
  );
}

/**
 * What the dashboard could not locate in this case.
 *
 * A case opens because it has a `controlDict`, not because it matches a known
 * layout -- so a case the rules were not written for shows the subset that lines
 * up and has to say which ones, and why, did not.  Each affected field carries
 * the same reason on hover; this is the one place that lists them together,
 * because a single field badge is easy to miss when a whole particle model is
 * absent.
 */
function RecognitionNotice() {
  const rec = useStore((s) => s.payload?.recognition);
  const reload = useStore((s) => s.reload);
  const t = useT();
  if (!rec || !rec.unrecognized.length) return null;

  const shown = rec.unrecognized.slice(0, 8);
  const rest = rec.unrecognized.length - shown.length;

  return (
    <div className="rounded-lg border border-warn/40 bg-warn/[0.07] px-3 py-2 backdrop-blur-xl">
      <p className="text-[11.5px] leading-relaxed text-warn">
        {t.t(
          "{n} parameters could not be recognized in this case (out of {total}; {a} recognized). They are marked Not found in the panel and are never written; use Open file to add on the parameter card to write the missing lines by hand, and the case is re-read once you save.",
          {
            n: rec.unrecognized.length,
            total: rec.total,
            a: rec.recognized,
          },
        )}
      </p>
      {rec.missing_files.length > 0 && (
        <p className="mt-1 truncate font-mono text-[10.5px] text-ink-3">
          {t.t("Files that could not be read: {files}", {
            files: rec.missing_files.map((m) => m.file).join(", "),
          })}
        </p>
      )}
      <ul className="mt-1 space-y-0.5">
        {shown.map((u) => (
          <li
            key={u.id}
            className="truncate font-mono text-[10.5px] text-ink-3"
            title={`${u.file}\n${u.reason}`}
          >
            {t.byId("param", u.id, u.label)} · {shortenFile(u.file)} · {u.reason}
          </li>
        ))}
        {rest > 0 && (
          <li className="text-[10.5px] text-ink-4">{t.t("…and {n} more", { n: rest })}</li>
        )}
      </ul>
      <button
        onClick={() => void reload()}
        className="mt-1.5 rounded border border-warn/40 px-1.5 py-0.5 text-[10.5px] text-warn transition hover:bg-warn/10"
        title={t.t("Re-read the current case's files; unwritten changes are kept")}
      >
        {t.t("Re-read")}
      </button>
    </div>
  );
}

/**
 * The only status there is: which case is open, what is still unwritten, and
 * whether a request is in flight.  One thin line is all that needs.
 */
function StatusBar({ busy }: { busy: boolean }) {
  const repo = useStore((s) => s.repo);
  const payload = useStore((s) => s.payload);
  const t = useT();
  // Counts only edits that differ from disk -- typing a value back to its
  // original must not read as "1 unwritten change".
  const count = useLiveEdits().length;

  return (
    <footer className="flex h-6 shrink-0 items-center gap-3 border-t border-line bg-wash/70 px-3 text-[10.5px] text-ink-4 backdrop-blur-xl">
      <span className="font-mono truncate">{repo}</span>
      <span className="ml-auto flex items-center gap-3">
        {payload && (
          <span className="font-mono">
            {t.t("{a}/{b} recognized · {c} editable", {
              a: payload.recognition.recognized,
              b: payload.recognition.total,
              c: payload.recognition.editable,
            })}
          </span>
        )}
        <span>
          {count > 0
            ? t.t("{n} unwritten changes", { n: count })
            : t.t("No unwritten changes")}
        </span>
        <span className={busy ? "text-accent" : ""}>{t.t(busy ? "Working…" : "Ready")}</span>
      </span>
    </footer>
  );
}
