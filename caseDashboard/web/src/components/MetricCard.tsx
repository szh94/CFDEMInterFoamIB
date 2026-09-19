import { flashKey, useStore } from "../store";
import { useT, type CardDrag } from "../hooks";
import { LEVEL_STYLE } from "../format";
import { IconGrip } from "./Icons";
import { Flash } from "./Flash";
import type { Metric } from "../types";

export function MetricCard({ metric, drag }: { metric: Metric; drag: CardDrag }) {
  const setFocus = useStore((s) => s.setFocusParam);
  const flash = useStore((s) => s.flashes[flashKey("metric", metric.id)]);
  const t = useT();
  const style = LEVEL_STYLE[metric.status];
  const refs = metric.source_refs;
  const label = t.byId("metric", metric.id, metric.label);

  return (
    <div
      data-card-id={metric.id}
      title={metric.formula || undefined}
      className={`glass-soft lift group relative rounded-md p-2 pl-4 ring-1 ring-inset ${style.ring}`}
    >
      {/* In the left gutter, on the severity dot's row.  A fixed `top` rather
          than a centring translate: the card grows a line or two as it gains a
          message, and a centred handle would drift with it. */}
      <span
        draggable
        title={t.t("Drag to reorder")}
        onDragStart={(e) => drag.start(metric.id, e)}
        onDragEnd={drag.end}
        className="absolute left-1 top-[10px] cursor-grab text-ink-4 opacity-30 transition-opacity select-none group-hover:opacity-100 active:cursor-grabbing"
      >
        <IconGrip width={12} height={12} className="block" />
      </span>

      <div className="flex items-baseline gap-2">
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${style.dot}`} />
        <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-2" title={label}>
          {label}
        </span>
        {/* A detail line *is* the value for a metric that needs one, so the
            header keeps only the name rather than printing the same numbers
            twice in two different formats. */}
        {!metric.detail && (
          <>
            <span className="tnum shrink-0 text-[13px] font-medium text-ink">
              {metric.display}
            </span>
            {metric.unit && (
              <span className="shrink-0 font-mono text-[10px] text-ink-4">{metric.unit}</span>
            )}
          </>
        )}
      </div>

      {/* Indented to the label: 6px dot + 8px gap. */}
      {metric.detail && (
        <div className="tnum mt-1 pl-3.5 text-[12px] text-ink">{metric.detail}</div>
      )}

      {metric.message && (
        <div className={`mt-1 text-[10.5px] leading-relaxed ${style.text}`}>
          {metric.message}
        </div>
      )}

      {refs.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {refs.map((r) => (
            <button
              key={r.param_id}
              onClick={() => setFocus(r.param_id)}
              title={t.t("Jump to {label} · {file}:{line}", {
                label: t.byId("param", r.param_id, r.label),
                file: r.file,
                line: r.line ?? "?",
              })}
              className="rounded border border-line-soft bg-panel-3/60 px-1.5 py-px text-[10px] text-ink-3 transition hover:border-accent/40 hover:text-accent"
            >
              {t.byId("param", r.param_id, r.label)}
            </button>
          ))}
        </div>
      )}

      <Flash token={flash} />
    </div>
  );
}
