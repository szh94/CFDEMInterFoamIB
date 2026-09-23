import { useMemo } from "react";
import { useStore } from "../store";
import { useGroupLevels, useLiveEdits, useT } from "../hooks";
import { IconCube, IconGrid, IconLink, IconParticles, IconSteps } from "./Icons";
import type { Group } from "../types";

const ICONS: Record<string, typeof IconGrid> = {
  geometry: IconCube,
  fluid: IconGrid,
  particle: IconParticles,
  coupling: IconLink,
  steps: IconSteps,
};

interface Props {
  groups: Group[];
  active: string;
  onChange: (id: string) => void;
}

export function TabBar({ groups, active, onChange }: Props) {
  const payload = useStore((s) => s.payload);
  const liveEdits = useLiveEdits();
  const levels = useGroupLevels();
  const t = useT();

  /** Per-tab dirty count, so the badge follows you across tabs. */
  const dirtyByGroup = useMemo(() => {
    const out: Record<string, number> = {};
    if (!payload) return out;
    const groupOf = new Map(payload.params.map((p) => [p.id, p.group]));
    for (const e of liveEdits) {
      const g = groupOf.get(e.id);
      if (g) out[g] = (out[g] ?? 0) + 1;
    }
    return out;
  }, [payload, liveEdits]);

  return (
    <nav className="glass-bar flex shrink-0 items-center gap-1 border-b border-line px-3">
      {groups.map((g) => {
        const Icon = ICONS[g.id] ?? IconGrid;
        const on = g.id === active;
        const dirty = dirtyByGroup[g.id] ?? 0;
        const level = levels[g.id];
        return (
          <button
            key={g.id}
            onClick={() => onChange(g.id)}
            className={`relative flex items-center gap-2 px-3.5 py-2.5 text-[12.5px] transition ${
              on ? "text-ink" : "text-ink-3 hover:text-ink-2"
            }`}
          >
            <Icon width={14} height={14} className={on ? "text-accent" : ""} />
            {t.byId("group", g.id, g.label)}
            {level && (
              <span
                className={`h-1.5 w-1.5 rounded-full ${level === "error" ? "bg-error" : "bg-warn"}`}
                title={t.t(
                  level === "error" ? "There is a consistency error" : "There is a consistency warning",
                )}
              />
            )}
            {dirty > 0 && (
              <span className="rounded bg-dirty/20 px-1 text-[10px] text-dirty">{dirty}</span>
            )}
            {on && (
              <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-accent" />
            )}
          </button>
        );
      })}

      <div className="ml-auto hidden items-center gap-2 pr-1 text-[11px] text-ink-4 lg:flex">
        {payload && (
          <span className="font-mono">{t.t("{n} files", { n: payload.files.length })}</span>
        )}
      </div>
    </nav>
  );
}
