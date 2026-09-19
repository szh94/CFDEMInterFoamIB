import { useStore } from "../store";
import { useT } from "../hooks";
import { LEVEL_STYLE } from "../format";
import { IconSpinner, IconSteps } from "./Icons";
import type { Level, StepEvidence, StepScript, StepStatus } from "../types";

/**
 * The colour a verdict gets, and the only place that mapping lives.
 *
 * Most states are neutral on purpose.  "There is nothing here yet", "the
 * frames are ready for the converter" and "the cleanup has not run since the
 * last test" are all ordinary states of a case mid-pipeline -- colouring any
 * of them as a warning would make a page that is meant to be read at a glance
 * read as an alarm.  Only `done` and `clean` are green, and `dirty` is
 * explicitly *not* a warning: the cleanup step's job is to leave the case bare,
 * so finding artifacts means a run is in progress, which is not a fault.
 */
const STATUS_LEVEL: Record<StepStatus, Level> = {
  done: "ok",
  clean: "ok",
  ready: "info",
  pending: "info",
  dirty: "info",
  unknown: "info",
};

/** The verdict word, keyed by status; the panel's own text, so translated. */
const STATUS_WORD: Record<StepStatus, string> = {
  done: "Done",
  ready: "Ready to run",
  pending: "Not started",
  clean: "Cleaned",
  dirty: "Artifacts still present",
  unknown: "No check defined for this script",
};

/** An evidence line's own dot.  `absent` is as neutral as `present` -- for the
    cleanup step it is the wanted answer -- so nothing here is coloured. */
const EVIDENCE_LEVEL: Record<StepEvidence["state"], Level> = {
  present: "ok",
  partial: "info",
  absent: "info",
};

const EVIDENCE_WORD: Record<StepEvidence["state"], string> = {
  present: "Present",
  partial: "Partial",
  absent: "Missing",
};

/**
 * The fourth tab: the case's `step*.sh` pipeline, one card per script.
 *
 * Every card answers the same question -- has this script been run, judged only
 * by what it left on disk.  Nothing here executes anything: the panel's contract
 * is that it reads and writes dictionaries and nothing else, so there is no
 * "run" button, only a re-check of the directory.
 */
export function StepsPanel() {
  const scripts = useStore((s) => s.scripts);
  const loading = useStore((s) => s.scriptsLoading);
  const loadScripts = useStore((s) => s.loadScripts);
  const t = useT();

  if (!scripts) {
    return (
      <div className="flex h-40 flex-col items-center justify-center gap-2 text-ink-3">
        <IconSpinner width={18} height={18} className="text-accent" />
        <p className="text-[12px]">{t.t("Checking the scripts…")}</p>
      </div>
    );
  }

  const done = scripts.filter((s) => s.status === "done").length;

  return (
    <div className="space-y-3">
      <div className="glass flex items-center gap-2 rounded-lg px-3 py-2">
        <IconSteps width={14} height={14} className="shrink-0 text-accent" />
        <span className="text-[12px] text-ink-2">
          {t.t("{n}/{m} steps complete", { n: done, m: scripts.length })}
        </span>
        <button
          onClick={() => void loadScripts()}
          disabled={loading}
          className="ml-auto flex shrink-0 items-center gap-1.5 rounded border border-line px-2 py-0.5 text-[11px] text-ink-3 transition hover:bg-panel-2 disabled:opacity-50"
        >
          {loading && <IconSpinner width={11} height={11} className="text-accent" />}
          {t.t("Re-check")}
        </button>
      </div>

      {scripts.length === 0 ? (
        <div className="p-8 text-center text-[12px] text-ink-4">
          {t.t("No step scripts were found in this case.")}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {scripts.map((script) => (
            <StepCard key={script.id} script={script} />
          ))}
        </div>
      )}
    </div>
  );
}

function StepCard({ script }: { script: StepScript }) {
  const t = useT();
  const style = LEVEL_STYLE[STATUS_LEVEL[script.status]];

  return (
    <section className="glass lift flex flex-col overflow-hidden rounded-lg">
      <header className="border-b border-line-soft bg-wash px-3 py-1.5">
        <div className="flex items-center gap-2">
          <span className="shrink-0 rounded bg-accent/15 px-1.5 py-0.5 font-mono text-[10.5px] text-accent">
            {t.t("Step {n}", { n: script.step })}
          </span>
          <span
            className="min-w-0 truncate font-mono text-[11.5px] text-ink"
            title={script.script}
          >
            {script.script}
          </span>
        </div>
        <p className="mt-0.5 truncate text-[10.5px] text-ink-4" title={script.title}>
          {t.byId("step", script.check, script.title)}
        </p>
      </header>

      <div className="space-y-1.5 px-3 py-2">
        <p className={`flex items-center gap-1.5 text-[11.5px] ${style.text}`}>
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${style.dot}`} />
          {t.t(STATUS_WORD[script.status])}
        </p>

        {script.evidence.length > 0 && (
          <ul className="space-y-0.5 border-t border-line-soft pt-1.5">
            {script.evidence.map((row) => (
              <li key={row.path} className="flex items-center gap-2 text-[10.5px]">
                <span
                  className={`h-1 w-1 shrink-0 rounded-full ${LEVEL_STYLE[EVIDENCE_LEVEL[row.state]].dot}`}
                  title={t.t(EVIDENCE_WORD[row.state])}
                />
                <span className="min-w-0 flex-1 truncate font-mono text-ink-3" title={row.path}>
                  {row.path}
                </span>
                {row.detail && (
                  <span className="shrink-0 font-mono text-ink-4">{row.detail}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
