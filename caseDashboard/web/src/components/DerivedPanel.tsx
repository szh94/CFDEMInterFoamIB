import { useState, type ReactNode } from "react";
import { useStore } from "../store";
import { useCardDrag, useOrderedMetrics, useT } from "../hooks";
import { CardSlot } from "./CardSlot";
import { ConsistencyList } from "./ConsistencyList";
import { MetricCard } from "./MetricCard";
import { IconCheck, IconChevron, IconGrid, IconUndo } from "./Icons";
import type { Level, Metric } from "../types";

type Filter = "all" | "issue";

export function DerivedPanel() {
  const derived = useStore((s) => s.derived);
  const metricsOrder = useStore((s) => s.cardOrder.metrics);
  const checksOrder = useStore((s) => s.cardOrder.checks);
  const resetCardOrder = useStore((s) => s.resetCardOrder);
  const [filter, setFilter] = useState<Filter>("all");
  // Before the list is filtered, and before anything can return early.
  const drag = useCardDrag("metrics");
  const metrics = useOrderedMetrics();
  const t = useT();

  const summary = derived?.summary;

  const shown = metrics.filter((m: Metric) => {
    if (filter === "issue") return m.status === "warn" || m.status === "error";
    return true;
  });

  return (
    <div className="glass lift flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg">
      {/* ---- summary ---- */}
      <div className="shrink-0 border-b border-line-soft bg-wash px-3 py-2.5">
        <div className="flex items-center gap-2">
          <IconGrid width={13} height={13} className="text-accent" />
          <span className="text-[12px] font-medium">{t.t("Derived metrics and checks")}</span>
          {summary && (
            <span className="ml-auto flex items-center gap-1.5 text-[10.5px]">
              <Chip level="error" n={summary.errors} />
              <Chip level="warn" n={summary.warnings} />
            </span>
          )}
        </div>
        {derived ? (
          <p className="mt-1 text-[10.5px] leading-relaxed text-ink-4">
            {t.t("Values recompute as you edit, so cross-file mismatches surface before anything is written.")}
          </p>
        ) : (
          <p className="mt-1 text-[10.5px] text-ink-4">{t.t("Computing…")}</p>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {/* ---- metrics ---- */}
        <Section
          title={t.t("Metrics")}
          right={
            <div className="flex items-center gap-1">
              {/* Alongside the filter, not instead of it. */}
              {metricsOrder.length > 0 && (
                <ResetOrder
                  title={t.t("Reset order")}
                  label={t.t("Reset the card order to the default")}
                  onClick={() => resetCardOrder("metrics")}
                />
              )}
              <div className="flex gap-0.5 rounded border border-line p-0.5">
                {(["all", "issue"] as Filter[]).map((f) => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={`rounded px-1.5 py-0.5 text-[10px] transition ${
                      filter === f ? "bg-accent/20 text-accent" : "text-ink-3 hover:text-ink"
                    }`}
                  >
                    {t.t(f === "all" ? "All" : "Issues only")}
                  </button>
                ))}
              </div>
            </div>
          }
        >
          {shown.length === 0 ? (
            <Empty text={t.t(filter === "issue" ? "No metrics have issues" : "No metrics")} />
          ) : (
            <div className="space-y-1.5">
              {shown.map((m) => (
                <CardSlot key={m.id} id={m.id} drag={drag} section="metrics">
                  <MetricCard metric={m} drag={drag} />
                </CardSlot>
              ))}
            </div>
          )}
        </Section>

        <div className="my-3 h-px bg-line-soft" />

        {/* ---- consistency ---- */}
        <Section
          title={t.t("Consistency")}
          right={
            checksOrder.length > 0 ? (
              <ResetOrder
                title={t.t("Reset order")}
                label={t.t("Reset the card order to the default")}
                onClick={() => resetCardOrder("checks")}
              />
            ) : undefined
          }
        >
          <ConsistencyList />
        </Section>

        {/* ---- inactive ---- */}
        {!!derived?.inactive_params.length && (
          <>
            <div className="my-3 h-px bg-line-soft" />
            <Inactive ids={derived.inactive_params} />
          </>
        )}
      </div>
    </div>
  );
}

/** The way back to the backend's own order.  Shown only once a section has
 * actually been rearranged; icon-only and unlabelled, like the rest of the
 * chrome, because this row already carries the All / Issues toggle. */
function ResetOrder({
  title,
  label,
  onClick,
}: {
  title: string;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      aria-label={label}
      className="rounded p-0.5 text-ink-4 transition hover:text-ink"
    >
      <IconUndo width={12} height={12} />
    </button>
  );
}

function Chip({ level, n }: { level: Level; n: number }) {
  const cls =
    level === "error"
      ? n > 0
        ? "border-error/40 bg-error/10 text-error"
        : "border-line text-ink-4"
      : n > 0
        ? "border-warn/40 bg-warn/10 text-warn"
        : "border-line text-ink-4";
  return (
    <span className={`rounded border px-1.5 py-0.5 font-mono ${cls}`}>
      {level === "error" ? "E" : "W"}
      {n}
    </span>
  );
}

function Section({
  title,
  right,
  children,
}: {
  title: string;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        <h3 className="text-[10.5px] font-medium uppercase tracking-wider text-ink-3">
          {title}
        </h3>
        <div className="ml-auto">{right}</div>
      </div>
      {children}
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="glass-soft flex items-center gap-2 rounded border px-2.5 py-2 text-[10.5px] text-ink-4">
      <IconCheck width={11} height={11} className="text-ok" />
      {text}
    </div>
  );
}

function Inactive({ ids }: { ids: string[] }) {
  const payload = useStore((s) => s.payload);
  const setFocus = useStore((s) => s.setFocusParam);
  const [open, setOpen] = useState(false);
  const t = useT();
  const labels = new Map(payload?.params.map((p) => [p.id, p.label]) ?? []);

  return (
    <section>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 text-[10.5px] uppercase tracking-wider text-ink-3 transition hover:text-ink-2"
      >
        <IconChevron
          width={11}
          height={11}
          className={`transition ${open ? "rotate-180" : ""}`}
        />
        {t.t("Inactive under the current configuration ({n})", { n: ids.length })}
      </button>
      {open && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {ids.map((id) => (
            <button
              key={id}
              onClick={() => setFocus(id)}
              className="rounded border border-line-soft bg-panel-3/50 px-1.5 py-0.5 text-[10px] text-ink-4 transition hover:border-accent/40 hover:text-accent"
            >
              {t.byId("param", id, labels.get(id) ?? id)}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
