import { useEffect, useMemo, useRef, useState } from "react";
import { useStore, valuesEqual } from "../store";
import { useIssueMap, useT } from "../hooks";
import { fmtNum, shortenFile } from "../format";
import { IconAlert, IconChevron } from "./Icons";
import type {
  CellValue,
  Param,
  ParamColumn,
  ParamValue,
  TableRow,
  TextLines,
  TripleTable,
  TripleValue,
} from "../types";

/** One value box, and the narrow one a row of several boxes spends its width on
    (two, or three, side by side).  A grouped row's boxes all take the narrow
    width so the row still reads as a set, and so a compact triple's last box
    lands on the right edge of the single box above it. */
const BOX_W = "w-[7rem]";
const BOX_W_NARROW = "w-[4.2rem]";

/**
 * The switchable group's own template -- "a single-column double-value box with
 * switches".  Each of the two values carries an Off/On pair beside it, so both
 * the pair and the box give up 30% of their width to keep the row on one line
 * in one column: the box is `4.2rem * 0.7`, the pair does it with padding (see
 * `ToggleChoice`'s `compact`).  See `BOX_W_SWITCH`'s caller for the fit.
 */
const BOX_W_SWITCH = "w-[2.95rem]"; // 4.2rem * 0.7

/**
 * A triple of full-width boxes spans two grid tracks, so it cannot grow its
 * label to fill the row the way a one-column row does -- that would shove the
 * three boxes to the far right of the second track.  Pinning the label to one
 * track's share of the spanning row instead puts the first box exactly under
 * the input of the row above:
 *
 *   `50%` of a two-track row's content is one track less 3px, and a one-column
 *   row spends `2 + 16 + 10 + 8 + 8 = 44px` on its own borders, padding, dirty
 *   dot and gaps before its label -- so the label gets `50% - (41px + box)`.
 *
 * Only a wide triple needs it: three 7rem boxes are about as wide as a column
 * and a half.  A compact triple (`Param.compact`) uses narrow boxes instead,
 * which leaves room for the label inside the row's own column.
 */
const PIN_W = "lg:w-[calc(50%-153px)]"; // 41 + 112 (one 7rem box)

interface Props {
  param: Param;
  /** The rest of a grouped quantity (see `Param.partners`): their boxes join
      this one's row and they get no row of their own.  Empty -> the plain
      single-param row this component has always been. */
  partners?: Param[];
  /** The params this one *owns* (see `Param.owner`): a phase's viscosity
      coefficients, whose lives follow from the model named in this row.  They
      get no row of their own either -- they are the box this row unfolds, and
      the ones on screen are the ones the model currently in force defines. */
  owned?: Param[];
  /** Set on an owned parameter whose owner is being switched *to* its model in
      this same write.  The file still says otherwise, so the backend has read
      it as `inactive`; but `owner_selects` looks at the pending value too, so
      the coefficient is writable now -- and switching a model and setting its
      coefficients should not take two rounds of Apply. */
  ownerSelected?: boolean;
  /** Set on an owned parameter, inside its owner's parameter list.  The cells
      there are a quarter of the card wide, which is room for a name and a box
      but not for a badge beside them -- so a badge is the list's to show (see
      the caller), not each row's, and the row does not wrap. */
  nested?: boolean;
  /** Highlighted by a click in the derived/consistency panel. */
  focused: boolean;
  inactive: boolean;
  /** Consistency problems naming this param. */
  issueLevel: "warn" | "error" | null;
}

export function ParamField({
  param,
  partners = [],
  owned = [],
  ownerSelected = false,
  nested = false,
  focused,
  inactive,
  issueLevel,
}: Props) {
  /** Open by default: under Newtonian the box holds the phase's ``nu``, which
      is a headline number rather than a detail, and a model the case has never
      run would otherwise hide the only box that model has.

      A folded row is the exception: the vertex table and the three
      marker-point pairs start closed, so the mesh card opens as a handful of
      one-line rows instead of six boxes and eight corners. */
  const [open, setOpen] = useState(!param.repeats && !param.collapsible);
  const setEdit = useStore((s) => s.setEdit);
  const setToggle = useStore((s) => s.setToggle);
  const clearEdit = useStore((s) => s.clearEdit);
  /** Per-box, for the ring: the row-level `focused` above says only that *one*
      of a pair was clicked, which does not say which box to point at. */
  const focusId = useStore((s) => s.focusParam);
  const ref = useRef<HTMLDivElement>(null);
  const t = useT();
  /** Needed for the owned parameters only: the row's own level comes in as a
      prop, because the panel merges it across the parts of a group. */
  const issues = useIssueMap();

  /**
   * A grouped row renders several params, so everything that used to read
   * `param` directly now reads one of `parts`.  With no partners `parts` is
   * `[param]` and `some`/`every`/`map` collapse back to the single-param
   * expressions -- which is what keeps the ungrouped rows byte-identical.
   */
  const parts = [param, ...partners];
  const grouped = partners.length > 0;
  /** A group whose lines are each switchable (the DEM walls): one Off/On
      control per box, beside that box. */
  const groupedToggle = grouped && param.toggle;

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
  const toggles = useStore((s) => s.toggles);
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

  /** What the box shows for one param: pending edit, else the file's value. */
  const valueOf = (p: Param): ParamValue => {
    if (p.id === param.id && product !== null) return product;
    const e = edits[p.id];
    return e !== undefined ? e : p.value;
  };
  const value = valueOf(param);

  /**
   * `vertices` and `particles` are *tables* rather than values (see
   * `Param.repeats`): `value` is one row per matched line, in the order the
   * file has them, and the panel lists them instead of showing one row of
   * boxes.
   *
   * `fileRows` is what is on disk; the pending table is what the user has
   * typed.  The two are kept apart on purpose: the edit carries all eight rows
   * ever pushed, so anything that still equals the file's own number has to be
   * recognised as untouched and handed back as the file spells it -- otherwise
   * a case written with `$xco1` for its corners would come out of the panel
   * with all twenty-four numbers frozen into literals.
   */
  const repeats = param.repeats && Array.isArray(value);
  const fileRows: TripleTable = param.repeats && Array.isArray(param.value)
    ? (param.value as TripleTable)
    : [];
  /** What the table has on screen: the pending one when the user has touched
      it, else the file's.  Its *length* is the user's business too -- the two
      buttons at the end add and drop rows -- so everything below reads the
      count off this rather than off the file. */
  const displayRows: TripleTable = Array.isArray(value) ? (value as TripleTable) : fileRows;

  /** The row's shape, as the backend declares it: the vertex table's three
      numbers, or a particle's note plus its eight.  A rule richer than the
      triple gets one box per column, each under its own label; a triple keeps
      the axis-lettered box it has always had. */
  const columns: ParamColumn[] = param.columns ?? [];
  const perColumn = repeats && columns.length > 3;
  const isTextColumn = (j: number) => columns[j]?.type === "text";

  /**
   * The columns in the order the panel draws them.  A free-text column is a
   * note *about* the numbers beside it, so it belongs after them rather than
   * in front of the row: the file leads each particle with its `#notes_pN:`
   * line, but on screen the eight numbers are what is being read.
   *
   * A display order only.  `Param.columns` is the order the file spells the
   * cells in and the writer formats the value by it, so a box that has moved
   * has to remember which cell it came from.  `sort` is stable, which is what
   * keeps the numbers among themselves in the file's own order.
   */
  const drawnColumns = columns
    .map((col, j) => ({ col, j }))
    .sort((a, b) => Number(isTextColumn(a.j)) - Number(isTextColumn(b.j)));

  /** The value typed into one cell, or `null` when its pending value is still
      the file's own -- i.e. nobody has touched it. */
  const typedCell = (i: number, j: number): CellValue | null => {
    const base = fileRows[i]?.[j];
    const pending = displayRows[i]?.[j];
    if (pending === undefined || pending === base) return null;
    return isTextColumn(j) ? String(pending) : Number(pending);
  };

  /**
   * One cell of a table, as the panel shows it: the file's number, unless
   * something pending speaks for it.  Two things can.  A macro whose source has
   * a pending edit -- the pointer or the domain extent being retyped -- because
   * the file will go on spelling `$xco1` and so the number it resolves to is
   * the new one; that is what makes the boxes follow a domain change as you
   * type, exactly like the derived metrics do.  And a literal typed into this
   * very cell, which replaces the macro outright.
   *
   * The typed literal wins: it is the more specific of the two, and it is what
   * the writer will actually put in the file.  A text column has no macro to
   * follow -- a note is not a number -- so only the file and the keyboard can
   * speak for it.
   */
  const cellOf = (i: number, j: number): CellValue => {
    const typed = typedCell(i, j);
    if (typed !== null) return typed;
    if (!isTextColumn(j)) {
      const src = param.macros?.[i]?.[j];
      const linked = src ? edits[src] : undefined;
      if (linked !== undefined && Number.isFinite(Number(linked))) return Number(linked);
    }
    const file = fileRows[i]?.[j];
    return file ?? (isTextColumn(j) ? "" : 0);
  };

  const shownRow = (i: number): TableRow =>
    (displayRows[i] ?? []).map((_, j) => cellOf(i, j));

  /**
   * The table as it should be written: every row the file already has goes back
   * as the numbers on disk -- which is what tells the writer to leave their
   * tokens alone -- and every row added since keeps the numbers it was given,
   * because there is no line for it in the file yet.
   *
   * Every control below commits through this rather than through what is on
   * screen: a box showing a linked `$xco1` has to go back as that row's file
   * number, or the writer would take the number as a literal and freeze the
   * macro.
   */
  const pendingRows = (): TripleTable =>
    displayRows.map((row, r) =>
      r < fileRows.length ? fileRows[r].map((f, c) => typedCell(r, c) ?? f) : [...row],
    );

  /** One cell of one row, committed as the whole table. */
  const commitRow = (i: number, next: TableRow) => {
    const current = shownRow(i);
    const j = next.findIndex((v, k) => v !== current[k]);
    if (j < 0) return;
    const rows = pendingRows();
    rows[i] = [...(rows[i] ?? [])];
    rows[i][j] = next[j];
    setEdit(param.id, rows);
  };

  /** One more row at the end: a corner at the origin, or a particle starting
      where the last one does (see `Param.row_seed`) -- a row to move into place
      rather than one to delete first. */
  const seedRow = (): TableRow => {
    const seed = param.row_seed;
    if (Array.isArray(seed) && seed.length === columns.length) return [...seed];
    return columns.map((c) => (c.type === "text" ? "" : 0));
  };
  const addRow = () => setEdit(param.id, [...pendingRows(), seedRow()]);
  const removeRow = () => setEdit(param.id, pendingRows().slice(0, -1));

  /** A `text` param's value: the lines, as the textarea spells them. */
  const textLines: TextLines = param.type === "text" && Array.isArray(value)
    ? (value as TextLines)
    : [];

  /**
   * The owned params that are on screen: the ones the *currently selected*
   * model defines, plus the ones no model governs (`p.model === null` -- a
   * phase's density, which sits in the same block and is read under every
   * model).  Read off the pending value rather than the one on disk, so picking
   * another model unfolds its coefficients straight away -- before anything is
   * applied, which is the point of choosing one.
   */
  const model = String(value ?? "");
  const ownedLive = owned.filter((p) => !p.model || p.model === model);
  /** The model on screen is not the one on disk, so what the file says about
      these parameters is one Apply out of date. */
  const switched = !valuesEqual(value, param.value);
  /** Whether the list below is one the file does not have yet -- either the
      backend already said so, or the switch above is what will make it so. */
  const creating = ownedLive.some(
    (p) => p.status === "create" || (switched && p.status === "inactive"),
  );
  /** Pending on/off state, still unwritten; `p.enabled` is what is on disk. */
  const enabledOf = (p: Param): boolean => {
    const tog = toggles[p.id];
    return tog !== undefined ? tog : p.enabled;
  };
  const dirtyOf = (p: Param): boolean => {
    const e = edits[p.id];
    return (
      (e !== undefined && !valuesEqual(e, p.value)) ||
      (p.toggle && enabledOf(p) !== p.enabled)
    );
  };
  const dirty = parts.some(dirtyOf);

  /**
   * A toggle param is editable exactly while its line is live and found.  Both
   * halves of that use the *pending* state: switching On for a line that is
   * still commented out on disk has to open the box, otherwise there would be
   * no way to set the value in the same write.  These are not "read-only"
   * failures, so they get no badge -- the Off/On pair says which state it is in.
   */
  const locatableOf = (p: Param): boolean => p.status === "ok" || p.status === "disabled";
  const disabledFor = (p: Param): boolean =>
    p.toggle
      ? !enabledOf(p) || !locatableOf(p)
      : (!p.editable && !(ownerSelected && p.status === "inactive")) || p.readonly;
  const disabled = disabledFor(param);
  /** Nothing to comment or un-comment when the line could not be found at all.
      Per param, because a grouped row switches each of its lines on its own. */
  const toggleLockOf = (p: Param): boolean => p.toggle && !locatableOf(p);

  /** One param's Off/On pair.  A plain row puts it between the label and the
      box; a grouped row puts one beside each of its boxes, `compact` -- that
      row is the one that has to fit two pairs and two boxes in one column. */
  const switchFor = (p: Param, compact = false) => (
    <span className="flex shrink-0 overflow-hidden rounded border border-line bg-field">
      <ToggleChoice
        label={t.t("Off")}
        active={!enabledOf(p)}
        disabled={toggleLockOf(p)}
        compact={compact}
        onClick={() => setToggle(p.id, false)}
      />
      <ToggleChoice
        label={t.t("On")}
        active={enabledOf(p)}
        disabled={toggleLockOf(p)}
        compact={compact}
        onClick={() => setToggle(p.id, true)}
        className="border-l border-line"
      />
    </span>
  );

  const outOfRangeFor = (p: Param): boolean => {
    if (!p.range || disabledFor(p)) return false;
    const [lo, hi] = p.range;
    const v = valueOf(p);
    const nums = Array.isArray(v) ? v : [v];
    return nums.some((n) => typeof n === "number" && (n < lo || n > hi));
  };
  const outOfRange = outOfRangeFor(param);

  useEffect(() => {
    if (focused && ref.current) {
      ref.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [focused]);

  /** Only a failed lookup is "unresolved"; `readonly` is a healthy status and
      used to be mislabelled with the same red badge. */
  const unresolvedOf = (p: Param): boolean =>
    p.status === "unresolved" || p.status === "ambiguous" || p.status === "missing";

  /** The other particle-creation route: located, but this case does not use it.
      Not a failure, so it gets a neutral badge rather than the red one. */
  const unusedOf = (p: Param): boolean => p.status === "unused";

  /** An optional setting this case leaves out: the solver falls back on its own
      default, so there is no line to add and nothing to report.  Neutral badge,
      like `unused` -- the difference is only in what it says. */
  const optionalOf = (p: Param): boolean => p.status === "optional";

  /** A coefficient whose model *is* the one selected but whose line the case
      does not have.  Ordinary and writable -- the writer adds the line on
      apply, and under Newtonian there is nothing to add at all -- so the badge
      has to say "not written yet", never "something is wrong".
      `ownerSelected` folds in the parameter the case has *not* caught up with
      yet: the file still names the old model, so the backend called it
      `inactive`, but the pending switch is exactly what makes it live. */
  const createOf = (p: Param): boolean =>
    p.status === "create" || (ownerSelected && p.status === "inactive");

  /** Some optional settings still mean something definite when the line is
      gone (a water box with no lower corner starts at the origin).  Then the
      box shows that number -- the backend reports it as `value`, so nothing
      here has to invent one -- and only the wording of the hint changes. */
  const settledAbsentOf = (p: Param): boolean => optionalOf(p) && p.default_when_absent;

  /**
   * Badges belong to the row, not to a box, so a group has to agree on one.
   *
   * The parts do not always come from the same kind of rule -- the water box's
   * lower bound is `optional` while its upper bound is an ordinary scalar -- so
   * a failure or an absence is shown when *any* part has it.  `every` there
   * would swallow a red *Not found* whenever only one part failed, which is
   * exactly the case the badge exists for.  Which part it refers to is in the
   * hint, one block per part.
   *
   * `unused` is the exception: it follows from `alt`, so all parts or none
   * always have it, and `every` says what is meant either way.
   */
  const unresolved = parts.some(unresolvedOf);
  const unused = parts.every(unusedOf);
  const optional = parts.some(optionalOf);
  const settledAbsent = parts.some(settledAbsentOf);
  const created = !nested && parts.some(createOf);

  /**
   * A triple input is three boxes plus the axis letters.  At full width that is
   * about a column and a half, so the row spans two tracks for its label to
   * have anywhere to sit.  A compact triple (`Param.compact`) spends the narrow
   * width on each box instead, which leaves room for the label inside the row's
   * own column -- so the row stays where it is, and with the label grown to
   * fill the gap its boxes end at the same right edge as the rows above.
   */
  const triple = param.type === "float3" || param.type === "int3";
  const compactTriple = triple && param.compact;
  const wideTriple = triple && !param.compact;
  const boxW = compactTriple ? BOX_W_NARROW : BOX_W;
  /** A block of free text: its box is the whole width of the card, so the row
      keeps that width too rather than squeezing the box into one column. */
  const text = param.type === "text";

  /**
   * Everything the row used to spell out underneath itself.  A paragraph of
   * help under every field buries the numbers the panel exists to show, so it
   * moves to the hover title -- except `unresolved`, which stays visible
   * because it means the tool cannot safely write this parameter at all.
   *
   * One block per part: a pair's two lines sit on different lines of the file,
   * so the `file:line` that opens each block is what says which box a note is
   * about.
   */
  const hintOf = (p: Param): string =>
    [
      `${shortenFile(p.source.file)}${p.source.line ? `:${p.source.line}` : ""}`,
      p.help,
      p.note,
      p.toggle
        ? enabledOf(p)
          ? t.t("Enabled: switching it off comments the line out")
          : t.t("Off: the line is commented out; switching it on uncomments it and writes the value back")
        : "",
      p.range
        ? t.t("Suggested range [{lo}, {hi}]", {
            lo: fmtNum(p.range[0]),
            hi: fmtNum(p.range[1]),
          })
        : "",
      createOf(p) ? t.t("Not in the file yet; it is written when applied") : "",
      issueLevel ? t.t("Differs from the same quantity in another file") : "",
      unusedOf(p) ? t.t("Unused: this case takes the other particle-creation route") : "",
      settledAbsentOf(p)
        ? t.t("Optional: this case leaves the line out, so the value shown is the default")
        : optionalOf(p)
          ? t.t("Optional: this case leaves the line out and the solver's own default applies")
          : "",
      unresolvedOf(p)
        ? t.t("Not found: matched {n} times (exactly 1 required)", { n: p.matches }) +
          (p.reason ? ` · ${p.reason}` : "")
        : "",
    ]
      .filter(Boolean)
      .join("\n");

  const hint = parts.map(hintOf).join("\n\n");

  /**
   * A row that owns parameters is one control in two boxes: the model to pick,
   * and the parameters that model is made of in a list underneath.  Unfolded,
   * the row takes the whole card width -- a strip of four coefficients squeezed
   * into one column would be a column of unreadable stubs.
   *
   * The list is a real sub-tree of `ParamField`s rather than a bespoke summary:
   * a coefficient is an ordinary parameter with its own box, edit and dirty
   * state, so it has to behave like one in every respect but position.
   */
  const expandable = ownedLive.length > 0 || repeats || param.collapsible;
  const expanded = expandable && open;

  /**
   * Whether the row's own boxes live in the fold rather than on the row.  True
   * for a table (its rows are all underneath) and for a collapsible group (that
   * is what the flag is for), and it is what the row reads as when closed: the
   * label, then how many things are inside.
   */
  const folded = repeats || param.collapsible;
  const foldedCount = repeats ? displayRows.length : parts.length;

  /**
   * A grouped row's boxes: one per part, side by side.  The group is one
   * quantity written as several lines -- left/right for a min and max, left to
   * right for x/y/z -- and each box keeps its own id, edit, switch and dirty
   * state.  The gap widens when the parts are switchable, so that a switch hugs
   * its own box rather than sitting halfway between two of them.
   *
   * A switchable row is its own template -- "a single-column double-value box
   * with switches": the pair and the box both give up 30% of their width
   * (`BOX_W_SWITCH`, and `compact` below), which is what keeps one row in one
   * column instead of having the boxes drop under the label.
   */
  const groupBoxes = (
    <div className={`flex ${groupedToggle ? "gap-2" : "gap-1"}`}>
      {parts.map((p) => (
        <span key={p.id} className="flex items-center gap-1">
          {p.toggle && switchFor(p, groupedToggle)}
          <Input
            param={p}
            value={valueOf(p)}
            disabled={disabledFor(p)}
            onCommit={(v) => setEdit(p.id, v)}
            outOfRange={outOfRangeFor(p)}
            width={groupedToggle ? BOX_W_SWITCH : BOX_W_NARROW}
            focused={focusId === p.id}
          />
        </span>
      ))}
    </div>
  );

  /**
   * A collapsible group's boxes, as its fold lists them: one per part, each
   * under the name the file gives that line.  The panel is showing the
   * definitions themselves here -- the six macros the mesh's corners are built
   * from -- so the label is the keyword the corner table resolves through
   * (`xco1` ...), not the panel's own name for the quantity ("Domain x max"),
   * which would leave the reader to work out which macro is which.
   */
  const markerBoxes = (
    <div className="grid grid-cols-1 gap-x-3 gap-y-0.5 sm:grid-cols-2 xl:grid-cols-4">
      {parts.map((p) => (
        <span key={p.id} className="flex items-center gap-1.5">
          <span className="w-9 shrink-0 truncate font-mono text-[10.5px] leading-none text-ink-4">
            {p.key}
          </span>
          <Input
            param={p}
            value={valueOf(p)}
            disabled={disabledFor(p)}
            onCommit={(v) => setEdit(p.id, v)}
            outOfRange={outOfRangeFor(p)}
            width={BOX_W_NARROW}
            focused={focusId === p.id}
          />
        </span>
      ))}
    </div>
  );

  /** The dot that says "this row differs from the file", and undoes it. */
  const dot = dirty ? (
    <button
      onClick={() => parts.forEach((p) => clearEdit(p.id))}
      title={t.t("On disk: {value} · click to undo this change", {
        value: parts.map((p) => String(p.value)).join(" / "),
      })}
      className="shrink-0 text-[10px] leading-none text-dirty transition hover:text-ink"
    >
      ●
    </button>
  ) : (
    <span className="w-[10px] shrink-0" />
  );

  return (
    <div
      ref={ref}
      title={hint}
      className={`flex items-center gap-2 rounded-md border px-2 py-1.5 transition ${
        nested ? "" : "flex-wrap"
      } ${expanded || text ? "lg:col-span-full" : wideTriple ? "lg:col-span-2" : ""} ${
        focused
          ? "border-accent/60 bg-accent/[0.07] shadow-[0_8px_24px_-12px_rgba(53,198,212,0.6)] ring-1 ring-accent/30"
          : "border-transparent hover:border-line hover:bg-wash-2"
      } ${inactive ? "opacity-45" : ""}`}
    >
      {dot}

      {/* Unit hugs the label, not the input: `Domain x min m` reads as a unit,
          `Domain x min ......... m` reads as a stray glyph in the gap.

          A triple row that spans two tracks pins its label rather than growing
          it -- see `PIN_W` for what that width is and why. */}
      <span
        className={`flex min-w-0 items-center gap-1.5 ${
          wideTriple ? `${PIN_W} lg:flex-none` : "flex-1"
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
      {/* A grouped row renders each part's pair beside its own box instead. */}
      {param.toggle && !grouped && switchFor(param)}

      {/* `Derived` rather than `Read-only` for a computed param: the difference
          that matters is not that it is locked but that it moves on its own.
          Asked through `disabledFor` rather than off `editable`, so a
          coefficient whose model is being switched to in this same write is
          not badged as locked while its box is open. */}
      {parts.every((p) => !p.toggle && disabledFor(p)) && (
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
          title={
            settledAbsent
              ? t.t("Optional: this case leaves the line out, so the value shown is the default")
              : t.t("Optional: this case leaves the line out and the solver's own default applies")
          }
        >
          {t.t("Optional")}
        </span>
      )}
      {created && (
        <span
          className="shrink-0 rounded border border-accent/40 bg-accent/10 px-1 py-px text-[9.5px] text-accent"
          title={t.t("Not in the file yet; it is written when applied")}
        >
          {t.t("Will be created when you apply")}
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

      {!folded &&
        (grouped ? (
          groupBoxes
        ) : text ? (
          <TextArea
            value={textLines}
            disabled={disabled}
            onCommit={(v) => setEdit(param.id, v)}
          />
        ) : (
          <Input
            param={param}
            value={value}
            disabled={disabled}
            onCommit={(v) => setEdit(param.id, v)}
            outOfRange={outOfRange}
            // Only a triple takes the card's width: for anything else the
            // default is the single box, whatever the neighbouring rows happen
            // to do -- a nested cell included: its box stays the width of every
            // other box in the card, so a column of them lines up with the rows
            // above.
            width={triple ? boxW : undefined}
          />
        ))}

      {expandable && (
        <button
          onClick={() => setOpen((v) => !v)}
          title={
            repeats
              ? t.t("The rows of this table, in the order the file lists them")
              : param.collapsible
                ? t.t("The macros the mesh's corners are built from; unfold to list them")
                : t.t("The parameters the selected model is written with")
          }
          className={`flex shrink-0 items-center gap-1 rounded border px-1.5 py-1 text-[10.5px] leading-none transition ${
            open
              ? "border-accent/50 bg-accent/10 text-accent"
              : "border-line text-ink-3 hover:bg-panel-2"
          }`}
        >
          {repeats
            ? t.t("{n} rows", { n: foldedCount })
            : param.collapsible
              ? t.t("{n} marker points", { n: foldedCount })
              : t.t("Parameters")}
          <IconChevron
            width={10}
            height={10}
            className={`transition-transform ${open ? "rotate-180" : ""}`}
          />
        </button>
      )}

      {expanded && (
        // Three things unfold here, and the row is one line in all of them:
        //
        // * the vertex table, one line per corner;
        // * a collapsible group's boxes, which are hidden while it is closed --
        //   the same set the row would have carried, just one line down, and
        //   each under the keyword the file spells it with;
        // * the coefficients of the model picked above -- four to a line, which
        //   is what a non-Newtonian model has: the four read as one group
        //   rather than as four full-width rows with the label at one end and
        //   its box at the other.
        //
        // The note in the third case is the list's, not each cell's: a cell is
        // a quarter of the card wide, and a badge beside the label there would
        // push the label out entirely -- so one line says for the four of them
        // what four badges would have said.
        <div className="w-full rounded border-l-2 border-accent/25 pl-2">
          {creating && (
            <div className="pb-0.5 text-[9.5px] leading-tight text-accent">
              {t.t("Will be created when you apply")}
            </div>
          )}
          {param.collapsible ? (
            markerBoxes
          ) : repeats ? (
            // One row of the table per line, in the order the file has them --
            // so the index in front is the one the block's own `hex` and
            // `patches` lines refer to, or the particle's own number.  It is a
            // fact about the line rather than a setting, so it is a plain label
            // and not a box: the index column is the gutter the buttons below
            // share.
            //
            // A rule of the triple's own shape keeps the one box it has always
            // had.  A wider row -- a particle is a note plus eight numbers --
            // gets one box per column instead, each under the name the backend
            // gives it, on a line of its own.
            <div
              className={
                perColumn
                  ? "grid grid-cols-1 gap-y-0.5"
                  : "grid grid-cols-1 gap-x-3 gap-y-0.5 sm:grid-cols-2 xl:grid-cols-4"
              }
            >
              {displayRows.map((_, i) => (
                <span
                  key={i}
                  className={`flex items-center gap-1.5 ${perColumn ? "flex-wrap" : ""}`}
                >
                  <span className="w-4 shrink-0 text-right font-mono text-[10.5px] leading-none text-ink-4">
                    {i}
                  </span>
                  {perColumn ? (
                    drawnColumns.map(({ col, j }) => (
                      <span key={col.name} className="flex items-center gap-1">
                        <span className="shrink-0 font-mono text-[10.5px] leading-none text-ink-4">
                          {t.t(col.label)}
                        </span>
                        <Cell
                          col={col}
                          value={shownRow(i)[j]}
                          disabled={disabled}
                          width={BOX_W_NARROW}
                          onCommit={(v) =>
                            commitRow(
                              i,
                              shownRow(i).map((x, k) => (k === j ? v : x)),
                            )
                          }
                        />
                      </span>
                    ))
                  ) : (
                    <Input
                      param={param}
                      value={shownRow(i) as TripleValue}
                      disabled={disabled}
                      outOfRange={false}
                      width={BOX_W_NARROW}
                      onCommit={(v) => commitRow(i, v as TableRow)}
                    />
                  )}
                </span>
              ))}
              {/* The table is only ever grown and trimmed at the end, which is
                  why these two are here rather than on a row of their own: they
                  follow the rows, so they land in the last one whatever the
                  count, and they read left to right in the order they act. */}
              <span className="flex items-center gap-1.5">
                <span className="w-4 shrink-0" />
                <button
                  onClick={addRow}
                  disabled={disabled}
                  title={t.t("Add a row at the end of the table")}
                  className="shrink-0 rounded border border-line px-1.5 py-1 text-[10.5px] leading-none text-ink-3 transition enabled:hover:bg-panel-2 enabled:hover:text-ink-2 disabled:opacity-40"
                >
                  {t.t("Add")}
                </button>
                <button
                  onClick={removeRow}
                  disabled={disabled || displayRows.length === 0}
                  title={t.t("Take the last row off the end of the table")}
                  className="shrink-0 rounded border border-line px-1.5 py-1 text-[10.5px] leading-none text-ink-3 transition enabled:hover:bg-panel-2 enabled:hover:text-ink-2 disabled:opacity-40"
                >
                  {t.t("Remove last")}
                </button>
              </span>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-x-3 gap-y-0.5 sm:grid-cols-2 xl:grid-cols-4">
              {ownedLive.map((p) => (
                <ParamField
                  key={p.id}
                  param={p}
                  ownerSelected={switched}
                  nested
                  focused={focusId === p.id}
                  inactive={false}
                  issueLevel={issues[p.id] ?? null}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------

/** One cell of a table row whose columns are not the triple's own.
 *
 * The column carries its own type, so the box follows from the column rather
 * than from the parameter: a note is a line of text, a diameter is a number.
 */
function Cell({
  col,
  value,
  disabled,
  width,
  onCommit,
}: {
  col: ParamColumn;
  value: CellValue | undefined;
  disabled: boolean;
  width: string;
  onCommit: (v: CellValue) => void;
}) {
  if (col.type === "text") {
    return (
      <StringBox
        value={String(value ?? "")}
        disabled={disabled}
        onCommit={onCommit}
      />
    );
  }
  return (
    <NumberBox
      value={Number(value ?? 0)}
      integer={col.type === "int"}
      disabled={disabled}
      outOfRange={false}
      width={width}
      onCommit={onCommit}
    />
  );
}

/**
 * A `text` param: the lines of the particle block's own comment, one per line.
 *
 * The block ends at a blank line, so a blank one here would take the particles
 * with it; the backend refuses the edit rather than writing it, and the box is
 * a textarea rather than a list of inputs because the lines are prose.
 */
function TextArea({
  value,
  disabled,
  onCommit,
}: {
  value: TextLines;
  disabled: boolean;
  onCommit: (v: TextLines) => void;
}) {
  const text = value.join("\n");
  const [draft, setDraft] = useState(text);
  useEffect(() => setDraft(text), [text]);
  return (
    <textarea
      disabled={disabled}
      value={draft}
      rows={Math.min(8, Math.max(2, text.split("\n").length))}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        const next = draft.split("\n");
        if (!valuesEqual(next, value)) onCommit(next);
      }}
      className="w-full resize-y rounded border border-line bg-field px-2 py-1 font-mono text-[12px] leading-snug text-ink transition focus:border-accent focus:outline-none disabled:opacity-60"
    />
  );
}

// ---------------------------------------------------------------------------

interface InputProps {
  param: Param;
  value: ParamValue;
  disabled: boolean;
  outOfRange: boolean;
  onCommit: (v: ParamValue) => void;
  /** Box width.  A grouped row narrows it so every box and the label still fit. */
  width?: string;
  /** Ring this box alone -- how a click on one source chip of a group points at
      the part it means, when the row-level highlight cannot. */
  focused?: boolean;
}

function Input({
  param,
  value,
  disabled,
  outOfRange,
  onCommit,
  width = BOX_W,
  focused = false,
}: InputProps) {
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
            width={width}
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
      width={width}
      focused={focused}
      // An absent optional line has no value, and `0` in a grey box would read
      // as one the file actually holds.  Not so when the absence itself has a
      // meaning: then `value` is that meaning and the box shows it.
      blank={param.status === "optional" && !param.default_when_absent}
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
  compact = false,
  onClick,
  className = "",
}: {
  label: string;
  active: boolean;
  disabled: boolean;
  /** 30% narrower, for the one row that carries a pair per value. */
  compact?: boolean;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`${compact ? "px-1 text-[10px]" : "px-2 text-[10.5px]"} py-1 leading-none transition disabled:opacity-40 ${className} ${
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
  /** Outranks `outOfRange` in the border: a pointer beats a diagnostic. */
  focused?: boolean;
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
  focused = false,
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
          focused
            ? "border-accent/60 ring-1 ring-accent/30"
            : outOfRange
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
