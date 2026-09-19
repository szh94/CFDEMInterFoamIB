import { useEffect, useMemo, useRef, useState } from "react";
import { useStore, valuesEqual } from "../store";
import { useT } from "../hooks";
import { fmtNum, shortenFile } from "../format";
import { IconAlert, IconChevron } from "./Icons";
import type { Param, ParamValue, TripleValue } from "../types";

interface Props {
  param: Param;
  /** Highlighted by a click in the derived/consistency panel. */
  focused: boolean;
  inactive: boolean;
  /** Consistency problems naming this param. */
  issueLevel: "warn" | "error" | null;
}

export function ParamField({ param, focused, inactive, issueLevel }: Props) {
  const edited = useStore((s) => s.edits[param.id]);
  const toggled = useStore((s) => s.toggles[param.id]);
  const setEdit = useStore((s) => s.setEdit);
  const setToggle = useStore((s) => s.setToggle);
  const clearEdit = useStore((s) => s.clearEdit);
  const ref = useRef<HTMLDivElement>(null);
  const t = useT();

  /**
   * A derived param is never typed into -- it *is* its sources -- so its
   * displayed value is recomputed here from the pending values of those sources
   * and follows them as you type, before anything is written.  The backend
   * derives the same value again; this copy exists only so the box tracks the
   * keyboard rather than the 150 ms derive round-trip.
   *
   * The combination follows the target's shape, exactly as `Ctx` does it: a
   * scalar is the product of its sources, a triple is the sources one per
   * component -- which is why this is a memo over raw slices rather than a
   * store selector: a triple's value is a fresh array, and a selector that
   * builds one every call renders forever (see `hooks.ts`).
   */
  const payload = useStore((s) => s.payload);
  const edits = useStore((s) => s.edits);
  const product = useMemo(() => {
    if (!param.product_of.length) return null;
    const nums: number[] = [];
    for (const id of param.product_of) {
      const pending = edits[id];
      const raw =
        pending !== undefined
          ? pending
          : payload?.params.find((p) => p.id === id)?.value;
      const n = Number(raw);
      if (!Number.isFinite(n)) return null;
      nums.push(n);
    }
    if (param.type === "float3" || param.type === "int3") {
      return nums.length === 3 ? ([nums[0], nums[1], nums[2]] as TripleValue) : null;
    }
    return nums.reduce((acc, n) => acc * n, 1);
  }, [param, payload, edits]);

  const value: ParamValue =
    product !== null ? product : edited !== undefined ? edited : param.value;
  /** Pending on/off state, still unwritten; `param.enabled` is what is on disk. */
  const enabled = toggled !== undefined ? toggled : param.enabled;
  const dirty =
    (edited !== undefined && !valuesEqual(edited, param.value)) ||
    (param.toggle && enabled !== param.enabled);

  /**
   * A toggle param is editable exactly while its line is live and found.  Both
   * halves of that use the *pending* state: switching On for a line that is
   * still commented out on disk has to open the box, otherwise there would be
   * no way to set the value in the same write.  These are not "read-only"
   * failures, so they get no badge -- the Off/On pair says which state it is in.
   */
  const locked = !param.editable || param.readonly;
  const locatable = param.status === "ok" || param.status === "disabled";
  const disabled = param.toggle ? !enabled || !locatable : locked;
  /** Nothing to comment or un-comment when the line could not be found at all. */
  const toggleLocked = param.toggle && !locatable;

  const outOfRange = (() => {
    if (!param.range || disabled) return false;
    const [lo, hi] = param.range;
    const nums = Array.isArray(value) ? value : [value];
    return nums.some((v) => typeof v === "number" && (v < lo || v > hi));
  })();

  useEffect(() => {
    if (focused && ref.current) {
      ref.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [focused]);

  /** Only a failed lookup is "unresolved"; `readonly` is a healthy status and
      used to be mislabelled with the same red badge. */
  const unresolved =
    param.status === "unresolved" ||
    param.status === "ambiguous" ||
    param.status === "missing";

  /** The other particle-creation route: located, but this case does not use it.
      Not a failure, so it gets a neutral badge rather than the red one. */
  const unused = param.status === "unused";

  /** An optional setting this case leaves out: the solver falls back on its own
      default, so there is no line to add and nothing to report.  Neutral badge,
      like `unused` -- the difference is only in what it says. */
  const optional = param.status === "optional";

  /**
   * A triple input is three boxes (~224 px) plus the axis letters, which leaves
   * a one-column cell too narrow for any label beside them.  Two columns is the
   * width such a row actually needs.
   */
  const triple = param.type === "float3" || param.type === "int3";

  /**
   * Everything the row used to spell out underneath itself.  A paragraph of
   * help under every field buries the numbers the panel exists to show, so it
   * moves to the hover title -- except `unresolved`, which stays visible
   * because it means the tool cannot safely write this parameter at all.
   */
  const hint = [
    `${shortenFile(param.source.file)}${param.source.line ? `:${param.source.line}` : ""}`,
    param.help,
    param.note,
    param.toggle
      ? enabled
        ? t.t("Enabled: switching it off comments the line out")
        : t.t("Off: the line is commented out; switching it on uncomments it and writes the value back")
      : "",
    param.range
      ? t.t("Suggested range [{lo}, {hi}]", {
          lo: fmtNum(param.range[0]),
          hi: fmtNum(param.range[1]),
        })
      : "",
    issueLevel ? t.t("Differs from the same quantity in another file") : "",
    unused ? t.t("Unused: this case takes the other particle-creation route") : "",
    optional
      ? t.t("Optional: this case leaves the line out and the solver's own default applies")
      : "",
    unresolved
      ? t.t("Not found: matched {n} times (exactly 1 required)", { n: param.matches }) +
        (param.reason ? ` · ${param.reason}` : "")
      : "",
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <div
      ref={ref}
      title={hint}
      className={`flex items-center gap-2 rounded-md border px-2 py-1.5 transition ${
        triple ? "lg:col-span-2" : ""
      } ${
        focused
          ? "border-accent/60 bg-accent/[0.07] shadow-[0_8px_24px_-12px_rgba(53,198,212,0.6)] ring-1 ring-accent/30"
          : "border-transparent hover:border-line hover:bg-wash-2"
      } ${inactive ? "opacity-45" : ""}`}
    >
      {dirty ? (
        <button
          onClick={() => clearEdit(param.id)}
          title={t.t("On disk: {value} · click to undo this change", { value: String(param.value) })}
          className="shrink-0 text-[10px] leading-none text-dirty transition hover:text-ink"
        >
          ●
        </button>
      ) : (
        <span className="w-[10px] shrink-0" />
      )}

      {/* Unit hugs the label, not the input: `Domain x min m` reads as a unit,
          `Domain x min ......... m` reads as a stray glyph in the gap.

          A triple row spans two of the three tracks, so growing the label to
          fill it would shove the three boxes to the far right of column 2.
          Pinning the label to one track's share instead puts the first box
          exactly under the input of the single-column row above: half of a
          spanning row's content box is one track less 3px, and a single-column
          row spends 156px per track on its own border, padding, dirty dot,
          gaps and input -- so the label gets `50% - 153px`. */}
      <span
        className={`flex min-w-0 items-center gap-1.5 ${
          triple ? "lg:w-[calc(50%-153px)] lg:flex-none" : "flex-1"
        }`}
      >
        <span className="truncate text-[12.5px] text-ink" title={param.id}>
          {t.byId("param", param.id, param.label)}
        </span>
        {param.unit && (
          <span className="shrink-0 font-mono text-[12.5px] text-ink-4">
            /{param.unit}
          </span>
        )}
      </span>

      {/* Off = comment the line out, On = put it back.  Two buttons rather
          than one switch because the wording is the action, not the state --
          and the highlighted half shows which state the line is in. */}
      {param.toggle && (
        <span className="flex shrink-0 overflow-hidden rounded border border-line bg-field">
          <ToggleChoice
            label={t.t("Off")}
            active={!enabled}
            disabled={toggleLocked}
            onClick={() => setToggle(param.id, false)}
          />
          <ToggleChoice
            label={t.t("On")}
            active={enabled}
            disabled={toggleLocked}
            onClick={() => setToggle(param.id, true)}
            className="border-l border-line"
          />
        </span>
      )}

      {/* `Derived` rather than `Read-only` for a computed param: the difference
          that matters is not that it is locked but that it moves on its own. */}
      {!param.toggle && locked && (
        <span
          className="shrink-0 rounded bg-panel-3 px-1 py-px text-[9.5px] text-ink-4"
          title={param.product_of.length ? param.help : t.t("Read-only; this parameter is never written")}
        >
          {param.product_of.length ? t.t("Derived") : t.t("Read-only")}
        </span>
      )}
      {inactive && (
        <span
          className="shrink-0 rounded bg-panel-3 px-1 py-px text-[9.5px] text-ink-4"
          title={t.t("Does not apply under the current configuration")}
        >
          {t.t("Inactive")}
        </span>
      )}
      {unused && (
        <span
          className="shrink-0 rounded bg-panel-3 px-1 py-px text-[9.5px] text-ink-4"
          title={t.t("This case creates its particles another way; these settings do not apply")}
        >
          {t.t("Unused")}
        </span>
      )}
      {optional && (
        <span
          className="shrink-0 rounded bg-panel-3 px-1 py-px text-[9.5px] text-ink-4"
          title={t.t("Optional: this case leaves the line out and the solver's own default applies")}
        >
          {t.t("Optional")}
        </span>
      )}
      {unresolved && (
        <span
          className="shrink-0 rounded border border-error/40 bg-error/10 px-1 py-px text-[9.5px] text-error"
          title={t.t("The pattern did not match exactly once, so it cannot be written safely")}
        >
          {t.t("Not found")}
        </span>
      )}
      {issueLevel && (
        <IconAlert
          width={11}
          height={11}
          className={`shrink-0 ${issueLevel === "error" ? "text-error" : "text-warn"}`}
        />
      )}

      <Input
        param={param}
        value={value}
        disabled={disabled}
        onCommit={(v) => setEdit(param.id, v)}
        outOfRange={outOfRange}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------

interface InputProps {
  param: Param;
  value: ParamValue;
  disabled: boolean;
  outOfRange: boolean;
  onCommit: (v: ParamValue) => void;
}

function Input({ param, value, disabled, outOfRange, onCommit }: InputProps) {
  if (param.type === "bool") {
    return (
      <Toggle
        on={value === true}
        disabled={disabled}
        onToggle={(next) => onCommit(next)}
      />
    );
  }

  if (param.type === "enum") {
    return (
      <div className="relative">
        <select
          disabled={disabled}
          value={String(value ?? "")}
          onChange={(e) => onCommit(e.target.value)}
          className="appearance-none rounded border border-line bg-field py-1 pl-2 pr-6 font-mono text-[12px] text-ink transition enabled:hover:border-line enabled:focus:border-accent enabled:focus:outline-none disabled:opacity-60"
        >
          {(param.options ?? []).map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
          {!param.options?.includes(String(value)) && (
            <option value={String(value ?? "")}>{String(value ?? "")}</option>
          )}
        </select>
        <IconChevron
          width={11}
          height={11}
          className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 text-ink-3"
        />
      </div>
    );
  }

  if (param.type === "float3" || param.type === "int3") {
    const arr = Array.isArray(value) ? value : [0, 0, 0];
    return (
      <div className="flex gap-1">
        {(["x", "y", "z"] as const).map((axis, i) => (
          <NumberBox
            key={axis}
            axis={axis}
            value={Number(arr[i] ?? 0)}
            integer={param.type === "int3"}
            disabled={disabled}
            outOfRange={false}
            width="w-[7rem]"
            onCommit={(n) => {
              const next: [number, number, number] = [
                Number(arr[0] ?? 0),
                Number(arr[1] ?? 0),
                Number(arr[2] ?? 0),
              ];
              next[i] = n;
              onCommit(next);
            }}
          />
        ))}
      </div>
    );
  }

  if (param.type === "string") {
    return (
      <StringBox value={String(value ?? "")} disabled={disabled} onCommit={onCommit} />
    );
  }

  return (
    <NumberBox
      value={Number(value ?? 0)}
      integer={param.type === "int"}
      disabled={disabled}
      outOfRange={outOfRange}
      width="w-[7rem]"
      // An absent optional line has no value, and `0` in a grey box would read
      // as one the file actually holds.
      blank={param.status === "optional"}
      onCommit={(n) => onCommit(param.type === "int" ? Math.round(n) : n)}
    />
  );
}

// ---------------------------------------------------------------------------

/**
 * One half of a toggle param's Off/On pair.  The active half is tinted; the
 * inactive one stays flat so the pair reads as a state, not as two buttons of
 * equal weight.
 */
function ToggleChoice({
  label,
  active,
  disabled,
  onClick,
  className = "",
}: {
  label: string;
  active: boolean;
  disabled: boolean;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-2 py-1 text-[10.5px] leading-none transition disabled:opacity-40 ${className} ${
        active
          ? "bg-accent/15 font-medium text-accent"
          : "text-ink-4 enabled:hover:bg-panel-2 enabled:hover:text-ink-2"
      }`}
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------

interface NumberBoxProps {
  value: number;
  integer: boolean;
  disabled: boolean;
  outOfRange: boolean;
  width: string;
  axis?: string;
  /** No value to show: an em dash instead of the ``value`` fallback. */
  blank?: boolean;
  onCommit: (n: number) => void;
}

/**
 * Keeps the raw string while focused so partial input ("1e-", "-", "0.00")
 * does not get parsed and rewritten under the cursor.  Commits on blur/Enter.
 *
 * The seed text is remembered so that focusing a field and leaving it again
 * writes nothing: the displayed form is rounded (2.2222222e-3 shows as
 * "0.00222222"), and committing that back would silently move the value.
 */
function NumberBox({
  value,
  integer,
  disabled,
  outOfRange,
  width,
  axis,
  blank = false,
  onCommit,
}: NumberBoxProps) {
  const [draft, setDraft] = useState<string | null>(null);
  const seeded = useRef<string>("");
  const cancelled = useRef(false);
  const shown = draft ?? (blank ? "—" : fmtNum(value));

  const commit = () => {
    const aborted = cancelled.current;
    cancelled.current = false;
    if (draft === null || aborted) {
      setDraft(null);
      return;
    }
    const text = draft.trim();
    setDraft(null);
    // Untouched (or retyped back to the same text): leave the file alone.
    if (text === "" || text === seeded.current.trim()) return;
    const parsed = Number(text);
    if (Number.isNaN(parsed)) return;
    const next = integer ? Math.round(parsed) : parsed;
    if (next !== value) onCommit(next);
  };

  const focus = (el: HTMLInputElement) => {
    cancelled.current = false;
    seeded.current = shown;
    setDraft(shown);
    requestAnimationFrame(() => el.select());
  };

  return (
    <div className="relative">
      {axis && (
        <span className="pointer-events-none absolute left-1.5 top-1/2 -translate-y-1/2 font-mono text-[10px] text-ink-4">
          {axis}
        </span>
      )}
      <input
        type="text"
        inputMode="decimal"
        disabled={disabled}
        value={shown}
        onFocus={(e) => focus(e.target)}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            commit();
            (e.target as HTMLInputElement).blur();
          } else if (e.key === "Escape") {
            cancelled.current = true;
            setDraft(null);
            (e.target as HTMLInputElement).blur();
          }
        }}
        className={`tnum ${width} rounded border bg-field py-1 pr-2 text-right text-[12px] text-ink transition focus:outline-none disabled:opacity-60 ${
          axis ? "pl-5" : "pl-2"
        } ${
          outOfRange
            ? "border-warn/60 ring-1 ring-warn/25"
            : "border-line focus:border-accent"
        }`}
      />
    </div>
  );
}

function StringBox({
  value,
  disabled,
  onCommit,
}: {
  value: string;
  disabled: boolean;
  onCommit: (v: string) => void;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return (
    <input
      type="text"
      disabled={disabled}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => draft !== value && onCommit(draft)}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
      }}
      className="w-[10rem] rounded border border-line bg-field px-2 py-1 font-mono text-[12px] text-ink transition focus:border-accent focus:outline-none disabled:opacity-60"
    />
  );
}

function Toggle({
  on,
  disabled,
  onToggle,
}: {
  on: boolean;
  disabled: boolean;
  onToggle: (v: boolean) => void;
}) {
  return (
    <button
      disabled={disabled}
      onClick={() => onToggle(!on)}
      className={`flex items-center gap-2 rounded border border-line bg-field py-1 pl-1.5 pr-2.5 transition enabled:hover:border-line disabled:opacity-60`}
    >
      <span
        className={`relative h-3.5 w-7 rounded-full transition ${on ? "bg-accent/70" : "bg-line"}`}
      >
        <span
          className={`absolute top-0.5 h-2.5 w-2.5 rounded-full bg-ink transition-all ${
            on ? "left-[1.05rem]" : "left-0.5"
          }`}
        />
      </span>
      <span className={`font-mono text-[11px] ${on ? "text-accent" : "text-ink-3"}`}>
        {on ? "on" : "off"}
      </span>
    </button>
  );
}
