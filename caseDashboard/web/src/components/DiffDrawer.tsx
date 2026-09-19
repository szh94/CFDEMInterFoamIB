import { useEffect, useMemo, useState } from "react";
import { useStore } from "../store";
import { useLiveEdits, useT } from "../hooks";
import { Translator } from "../i18n";
import { shortenFile } from "../format";
import { IconCheck, IconDiff, IconSpinner } from "./Icons";
import type { DiffRow, FileDiff } from "../types";

/**
 * Side-by-side proof of what will be written.  The writer only ever splices
 * the value span, so unchanged context -- trailing `//comment`s, `&`
 * continuations, CRLF -- is expected to show as identical rows.  That is the
 * whole reason the diff is shown before the write rather than after.
 */
export function DiffDrawer() {
  const open = useStore((s) => s.diffOpen);
  const preview = useStore((s) => s.preview);
  const busy = useStore((s) => s.busy);
  const apply = useStore((s) => s.apply);
  const close = useStore((s) => s.closeDiff);
  const liveEdits = useLiveEdits();
  const t = useT();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, busy, close]);

  if (!open || !preview) return null;

  const changed = preview.diffs.filter((d) => !d.byte_identical);
  const blocked = Object.entries(preview.validations ?? {});

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-base/75 backdrop-blur-sm"
        onClick={() => !busy && close()}
      />

      <div className="anim-in glass-strong relative flex max-h-[88vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl">
        {/* ---- header ---- */}
        <header className="flex shrink-0 items-center gap-3 border-b border-line px-4 py-3">
          <IconDiff width={16} height={16} className="text-accent" />
          <div>
            <h2 className="text-[13px] font-medium">{t.t("Write preview")}</h2>
            <p className="text-[11px] text-ink-3">
              {t.t("{f} files will change · {n} parameters · nothing written to disk yet", {
                f: changed.length,
                n: liveEdits.length,
              })}
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={close}
              disabled={busy}
              className="btn-glass rounded-md px-3 py-1.5 text-[12px] text-ink-2 transition disabled:opacity-40"
            >
              {t.t("Cancel")}
            </button>
            <button
              onClick={apply}
              disabled={busy || !changed.length}
              className="btn-gloss flex items-center gap-1.5 rounded-md bg-accent px-3.5 py-1.5 text-[12px] font-medium text-accent-ink disabled:opacity-40"
            >
              {busy ? <IconSpinner width={13} height={13} /> : <IconCheck width={13} height={13} />}
              {t.t("Write {n} files", { n: changed.length })}
            </button>
          </div>
        </header>

        {blocked.length > 0 && (
          <div className="shrink-0 border-b border-error/30 bg-error/[0.08] px-4 py-2">
            <div className="text-[11px] font-medium text-error">
              {t.t("These changes were refused (the rest will still be written):")}
            </div>
            <ul className="mt-1 space-y-0.5">
              {blocked.map(([id, reason]) => (
                <li key={id} className="flex items-baseline gap-2 text-[11px]">
                  <code className="shrink-0 font-mono text-ink-2">{labelOf(id)}</code>
                  <span className="text-error">{reason}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* ---- body ---- */}
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {changed.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-12 text-ink-3">
              <IconCheck width={22} height={22} className="text-ok" />
              <p className="text-[12.5px]">
                {t.t("The write is byte-for-byte identical to the files on disk; nothing would change.")}
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {changed.map((d) => (
                <FileDiffView key={d.file} diff={d} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function FileDiffView({ diff }: { diff: FileDiff }) {
  const [unified, setUnified] = useState(false);
  const t = useT();
  const rows = useMemo(
    () => diff.hunks.flatMap((h) => h.rows),
    [diff],
  );
  const added = diff.added ?? rows.filter((r) => r.type === "insert").length;
  const removed = diff.removed ?? rows.filter((r) => r.type === "delete").length;

  return (
    <section className="glass-soft overflow-hidden rounded-lg">
      <header className="flex items-center gap-2 border-b border-line-soft bg-wash px-3 py-2">
        <span className="font-mono text-[11.5px] text-ink-2">{shortenFile(diff.file)}</span>
        <span className="font-mono text-[10px] text-ok">+{added}</span>
        <span className="font-mono text-[10px] text-error">−{removed}</span>
        <button
          onClick={() => setUnified((v) => !v)}
          className="ml-auto rounded border border-line px-2 py-0.5 text-[10px] text-ink-3 transition hover:bg-wash-3 hover:text-ink"
        >
          {t.t(unified ? "Side by side" : "Unified")}
        </button>
      </header>

      {unified ? (
        <pre className="max-h-[26rem] overflow-auto bg-field px-3 py-2 font-mono text-[11px] leading-[1.6]">
          {diff.unified.split("\n").map((line, i) => (
            <div
              key={i}
              className={
                line.startsWith("+")
                  ? "bg-ok/[0.09] text-ok"
                  : line.startsWith("-")
                    ? "bg-error/[0.09] text-error"
                    : line.startsWith("@@")
                      ? "text-accent"
                      : "text-ink-4"
              }
            >
              {line || " "}
            </div>
          ))}
        </pre>
      ) : (
        <SideBySide rows={rows} />
      )}
    </section>
  );
}

function SideBySide({ rows }: { rows: DiffRow[] }) {
  return (
    <div className="max-h-[26rem] overflow-auto bg-field">
      <table className="w-full table-fixed border-collapse">
        <colgroup>
          <col className="w-10" />
          <col className="w-1/2" />
          <col className="w-10" />
          <col className="w-1/2" />
        </colgroup>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="align-top">
              <td className="select-none border-r border-line-soft px-1.5 text-right font-mono text-[10px] leading-[1.6] text-ink-4">
                {r.a_no ?? ""}
              </td>
              <td className={cellCls(r.type, "a")}>
                <code className="whitespace-pre-wrap break-all">
                  {r.a === null ? "" : r.a || " "}
                </code>
              </td>
              <td className="select-none border-x border-line-soft px-1.5 text-right font-mono text-[10px] leading-[1.6] text-ink-4">
                {r.b_no ?? ""}
              </td>
              <td className={cellCls(r.type, "b")}>
                <code className="whitespace-pre-wrap break-all">
                  {r.b === null ? "" : r.b || " "}
                </code>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Rejections are keyed by param id; show the human label where we have it. */
function labelOf(paramId: string): string {
  const s = useStore.getState();
  const param = s.payload?.params.find((p) => p.id === paramId);
  if (!param) return paramId;
  return new Translator(s.lang).byId("param", paramId, param.label);
}

function cellCls(type: DiffRow["type"], side: "a" | "b"): string {
  const base = "px-2 py-0 font-mono text-[11px] leading-[1.6] ";
  if (type === "replace")
    return base + (side === "a" ? "bg-error/[0.09] text-error" : "bg-ok/[0.09] text-ok");
  if (type === "delete") return base + (side === "a" ? "bg-error/[0.09] text-error" : "text-ink-4");
  if (type === "insert") return base + (side === "b" ? "bg-ok/[0.09] text-ok" : "text-ink-4");
  return base + "text-ink-3";
}
