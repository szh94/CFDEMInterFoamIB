import { useEffect, useRef, useState } from "react";
import { useStore } from "../store";
import { useT } from "../hooks";
import { IconChevron, IconSphere } from "./Icons";
import { recognitionLine } from "../format";

export function CaseSelector() {
  const cases = useStore((s) => s.cases);
  const casePath = useStore((s) => s.casePath);
  const payload = useStore((s) => s.payload);
  const selectCase = useStore((s) => s.selectCase);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const t = useT();

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const single = cases.length <= 1;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => !single && setOpen((v) => !v)}
        className={`btn-glass flex h-8 max-w-[22rem] items-center gap-2 rounded-md px-2.5 text-left ${
          single ? "cursor-default" : ""
        }`}
      >
        <IconSphere width={14} height={14} className="shrink-0 text-accent" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-medium leading-tight text-ink">
            {casePath ?? t.t("No case selected")}
          </span>
          {payload && (
            <span className="block truncate text-[10.5px] leading-tight text-ink-3">
              {recognitionLine(payload.recognition, t)}
            </span>
          )}
        </span>
        {!single && <IconChevron width={13} height={13} className="shrink-0 text-ink-3" />}
      </button>

      {open && (
        <div className="anim-in glass-strong absolute left-0 top-full z-40 mt-2 w-[24rem] overflow-hidden rounded-lg">
          {cases.map((c) => (
            <button
              key={c.path}
              onClick={() => {
                setOpen(false);
                if (c.path !== casePath) void selectCase(c.path);
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
          ))}
        </div>
      )}
    </div>
  );
}
