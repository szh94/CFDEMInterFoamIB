import { useMemo, useState } from "react";
import { useStore } from "../store";
import { useT } from "../hooks";
import { LEVEL_STYLE, shortenFile } from "../format";
import { IconCheck, IconChevron, IconTarget } from "./Icons";
import type { Consistency } from "../types";

/**
 * Cross-file consistency: the reason this dashboard exists.  Every entry can
 * point back at the fields that produced it, and every field below the finding
 * is a live value, so the numbers here change as you type -- always before
 * anything is written to disk.
 */
export function ConsistencyList() {
  const consistency = useStore((s) => s.derived?.consistency);
  const summary = useStore((s) => s.derived?.summary);
  const setFocus = useStore((s) => s.setFocusParam);
  const t = useT();

  const ordered = useMemo(() => {
    if (!consistency) return [];
    const rank = { error: 0, warn: 1, info: 2, ok: 3 } as const;
    return [...consistency].sort((a, b) => rank[a.level] - rank[b.level]);
  }, [consistency]);

  if (!consistency) {
    return <div className="px-3 py-4 text-[11.5px] text-ink-4">{t.t("Computing…")}</div>;
  }

  const allClear = summary?.errors === 0 && summary?.warnings === 0;

  return (
    <div className="space-y-1.5">
      {allClear && (
        <div className="flex items-center gap-2 rounded-md border border-ok/25 bg-ok/[0.07] px-2.5 py-2 text-[11.5px] text-ok backdrop-blur-xl">
          <IconCheck width={13} height={13} />
          {t.t("All cross-file consistency checks pass")}
        </div>
      )}

      {ordered.map((c) => (
        <Finding key={c.id} item={c} onFocus={setFocus} />
      ))}
    </div>
  );
}

function Finding({
  item,
  onFocus,
}: {
  item: Consistency;
  onFocus: (id: string) => void;
}) {
  const t = useT();
  const style = LEVEL_STYLE[item.level];
  const collapsible = item.sources.length > 0;
  // Controlled: a static `open` prop would be re-applied on every re-render
  // (i.e. on every keystroke), so a finding could never be collapsed.
  const [open, setOpen] = useState(item.level === "error" || item.level === "warn");

  return (
    <details
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
      className={`glass-soft lift group rounded-md ring-1 ring-inset ${style.ring}`}
    >
      <summary
        className={`flex cursor-pointer list-none items-start gap-2 px-2.5 py-2 ${
          collapsible ? "" : "pointer-events-none"
        }`}
      >
        <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${style.dot}`} />
        <span className="min-w-0 flex-1">
          <span className={`block text-[11.5px] font-medium ${style.text}`}>
            {item.title}
          </span>
          <span className="mt-0.5 block text-[10.5px] leading-relaxed text-ink-3">
            {item.message}
          </span>
        </span>
        {collapsible && (
          <IconChevron
            width={12}
            height={12}
            className="mt-0.5 shrink-0 text-ink-4 transition group-open:rotate-180"
          />
        )}
      </summary>

      {collapsible && (
        <div className="space-y-1 border-t border-line-soft px-2.5 py-2">
          {item.sources.map((s) => (
            <button
              key={`${s.param_id}-${s.line}`}
              onClick={() => onFocus(s.param_id)}
              className="flex w-full items-center gap-2 rounded border border-line-soft bg-panel-3/40 px-2 py-1 text-left transition hover:border-accent/40 hover:bg-panel-3"
            >
              <IconTarget width={10} height={10} className="shrink-0 text-ink-4" />
              <span className="min-w-0 flex-1 truncate text-[10.5px] text-ink-2">
                {t.byId("param", s.param_id, s.label)}
              </span>
              <span className="tnum shrink-0 font-mono text-[10px] text-ink-3">
                {String(s.value)}
              </span>
              <span className="shrink-0 font-mono text-[9.5px] text-ink-4">
                {shortenFile(s.file)}
                {s.line ? `:${s.line}` : ""}
              </span>
            </button>
          ))}
        </div>
      )}
    </details>
  );
}
