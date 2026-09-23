/** Shapes mirroring the Python backend responses verbatim. */

export type ParamType =
  | "float"
  | "int"
  | "bool"
  | "string"
  | "enum"
  | "float3"
  | "int3"
  /** Free-form lines of text -- the particle block's own comments. */
  | "text";

export type ParamStatus =
  | "ok"
  | "unresolved"
  | "ambiguous"
  | "missing"
  | "readonly"
  /** Toggle param whose line is commented out (Off). The value is still read. */
  | "disabled"
  /** The *other* mutually exclusive particle-creation route (see `Param.alt`):
      the rules read it fine, this case just does not take that route. */
  | "unused"
  /** An optional setting (see `Param.optional`) this case leaves out; the
      solver has a default for it, so there is nothing to fix and nothing to
      write. */
  | "optional"
  /** A model-owned parameter (see `Param.owner`) whose owner *does* select it
      but whose line this case does not have: editable, valued from the seed,
      and written as a new line when applied. */
  | "create"
  /** A model-owned parameter the owner does not select (`owner` names another
      model): read, but not part of this case and not writable. */
  | "inactive";

export type Scalar = number | string | boolean;
export type TripleValue = [number, number, number];
/** One cell of a table row: a number, or the text of a `text` column. */
export type CellValue = number | string;
/** One row of a `repeats` table: one entry per column (see `Param.columns`),
    which for the triple-shaped tables is the triple it has always been. */
export type TableRow = CellValue[];
/** A `repeats` param's value: one row per matched line, in file order. */
export type TripleTable = TableRow[];
/** A `text` param's value: one entry per line, as the file spells it. */
export type TextLines = string[];
export type ParamValue =
  | Scalar
  | TripleValue
  | TableRow
  | TripleTable
  | TextLines
  | null;

/** One column of a `repeats` table's row, as the writer will format it. */
export interface ParamColumn {
  name: string;
  type: ParamType;
  /** What the panel prints above the column; also the i18n key. */
  label: string;
  unit: string;
  /** For an `enum` column: the choices its box offers. A cell the file spells
      differently is shown as itself -- the list is a convenience, not a
      filter. */
  options: string[] | null;
  /** The cell is not on the row's own line: it comes from the block the row
      sits in (`mesh.faces`'s patch name), so it is shown for context and
      never edited. */
  derived: boolean;
  /** A CSS length the rule fixes the box at, so the column's boxes line up
      down the table; `null` -> the panel's own width for the cell's type. */
  width: string | null;
}

export interface SourceRef {
  file: string;
  line: number | null;
}

export interface Param {
  id: string;
  group: string;
  /** Own card title inside the file; null -> the card is the file itself. */
  card: string | null;
  label: string;
  value: ParamValue;
  unit: string;
  type: ParamType;
  options: string[] | null;
  range: [number, number] | null;
  help: string;
  note: string;
  default: ParamValue;
  status: ParamStatus;
  readonly: boolean;
  /** For an `optional` param whose absent state has a settled value (see
      `Param.default_when_absent`): `value` is that default rather than null, so
      the box shows a number -- greyed out, never written -- and the derived
      metrics compute with it. */
  default_when_absent: boolean;
  /** `status === "ok"`, not readonly and not derived: the only params we write. */
  editable: boolean;
  /** Non-empty when the value is derived from these params': their product for a
      scalar, one source per component for a triple. The panel shows it read-only
      and the backend re-syncs the line on every write. */
  product_of: string[];
  /** The keyword the line is anchored on -- what the file calls this parameter
      (`xco1`), which is also the name a macro goes by. Where a folded row lists
      its parts, this is the label each box gets: the panel is showing the
      definitions themselves rather than the panel's own name for them. */
  key: string;
  /** The rest of a set of sibling lines shown on one row (the min and max of one
      domain extent, the x/y/z of one decomposition): the panel folds the named
      params into this one's row and skips rendering them on their own.
      Display-only -- every id keeps its own rule, line and edit. Only the first
      of a group carries it. */
  partners: string[];
  /** A triple laid out to fit inside one column: three narrow boxes with the
      label grown to fill, instead of a row spanning two columns. Display-only.
      The point is that the last of the three boxes then lines up with the single
      box of the rows above it. */
  compact: boolean;
  /** The row's boxes sit behind a fold: until it is opened the row is its
      label and a count (see `Param.collapsible`). Display-only, and it folds
      the whole group -- the row itself plus its `partners`. */
  collapsible: boolean;
  /** The rule matches a *list*: `value` is a table of triples, one row per
      matched line, rather than one triple. The panel renders one row of boxes
      per line instead of a single row. */
  repeats: boolean;
  /** The rule declared its own columns, so the panel draws one box per column
      rather than the triple's own x/y/z. The vertex table's three columns
      *are* the axes; a two-column table of its own is not a triple. */
  per_column: boolean;
  /** For a `repeats` param, the parameter each component's token came from --
      `macros[row][axis]`, or `null` where the file spells a literal number.
      This is what carries a pending edit of a source (a domain extent) into a
      row the user is not editing. `null` for every other param. */
  macros: (string | null)[][] | null;
  /** For a `repeats` param: every column of a row, across all the lines the
      row is written on (see `Param.row_lines` in the backend).  The panel
      labels and types each box from this rather than assuming the triple's own
      x/y/z.  Empty for every other param. */
  columns: ParamColumn[];
  /** For a `repeats` param: what the Add button writes into a new row.  The
      vertex table starts a corner at the origin; the particle table starts one
      where the last particle is. */
  row_seed: TableRow | null;
  /** Whether rows may be added to the end of the table and taken off it. False
      where a row is not self-contained -- a patch header introduces a block of
      faces the writer cannot build from the header alone -- and the panel then
      offers no Add/Remove. */
  row_append: boolean;
  /** How many of the table's rows share one line. A row of a few narrow cells
      leaves most of the card empty, so several read better side by side. */
  row_per_line: number;
  /** The line can be commented out to switch it off (see `enabled`). */
  toggle: boolean;
  /** For a toggle param: whether its line is live. Always true otherwise. */
  enabled: boolean;
  /** The parameter that decides whether this one is live at all, and the value
      of it under which it applies (`null` for an ordinary parameter).  The
      panel hangs such a parameter off its owner's row instead of giving it one
      of its own -- see `ParamField`'s `owned`. */
  owner: string | null;
  /** The model `owner` has to name for this parameter to apply. */
  model: string | null;
  /** The `<Model>Coeffs` sub-dictionary this parameter lives in, `null` when it
      is written straight into the block above. */
  block: string | null;
  reason: string;
  matches: number;
  source: SourceRef;
  scope: string | null;
}

export interface Group {
  id: string;
  label: string;
  blurb: string;
  /** What the tab holds: the ordinary case is fields, `scripts` is the
      `step*.sh` pipeline, rendered from `/api/steps` rather than the payload,
      and `geometry` is the dashboard's own picture of the mesh -- the one tab
      the backend does not send (see `App`'s `GEOMETRY`), so it is typed here
      rather than left out. */
  kind: "params" | "scripts" | "geometry";
  param_ids: string[];
}

/** How a `step*.sh` script's artifacts look on disk.
 *
 * `clean`/`dirty` belong to the cleanup step alone -- it is the one script
 * whose success is the absence of files, so its verdict is worded as a state
 * rather than as progress.  `ready` is "the input is there, the output is not
 * yet", which for the two post-processing steps includes the hand-made frames
 * and the dumps a run leaves behind. */
export type StepStatus = "done" | "ready" | "pending" | "clean" | "dirty" | "unknown";

/** One thing a script's check looked for.  `detail` is only ever a number with
    a unit -- every word around it is the panel's own. */
export interface StepEvidence {
  path: string;
  state: "present" | "absent" | "partial";
  detail: string;
}

/** One `step*.sh` in the case directory, against what it has produced. */
export interface StepScript {
  id: string;
  script: string;
  step: number;
  token: string;
  /** Which check the script's name earned; `unknown` when none did. */
  check: string;
  /** English fallback title, keyed by `check` for translation. */
  title: string;
  status: StepStatus;
  evidence: StepEvidence[];
}

export interface StepsPayload {
  path: string;
  scripts: StepScript[];
}

/** A parameter the rules could not locate in this case. */
export interface UnrecognizedParam {
  id: string;
  label: string;
  file: string;
  matches: number;
  /** Why it failed -- this is the prompt shown for the parameter. */
  reason: string;
}

/** How much of the parameter list this case matched.
 *
 * There is one list, not one per case, so opening a case the list was not
 * written for is not an error: whatever lines up is editable and the rest is
 * reported here and marked Not found in the panel. */
export interface Recognition {
  total: number;
  recognized: number;
  editable: number;
  unrecognized: UnrecognizedParam[];
  /** Files the reader could not open at all. */
  missing_files: { file: string; error: string }[];
}

export interface CasePayload {
  path: string;
  abs_path: string;
  groups: Group[];
  params: Param[];
  files: string[];
  /** What each dictionary is for, keyed by path. Missing -> show the path alone. */
  file_labels: Record<string, string>;
  recognition: Recognition;
  writable: boolean;
}

export type Level = "ok" | "info" | "warn" | "error";

export interface Metric {
  id: string;
  label: string;
  value: number | string | boolean | null;
  display: string;
  unit: string;
  status: Level;
  message: string;
  formula: string;
  /** A value too wide for the header slot -- three components, each wanting its
      own axis letter.  When set it is rendered on its own line under the name,
      and the right-aligned `display` is left out. */
  detail: string;
  source_refs: { param_id: string; label: string; file: string; line: number | null; value: unknown }[];
}

export interface Consistency {
  id: string;
  level: Level;
  title: string;
  message: string;
  sources: { param_id: string; label: string; file: string; line: number | null; value: unknown }[];
  param_ids: string[];
}

export interface Derived {
  metrics: Metric[];
  consistency: Consistency[];
  inactive_params: string[];
  values: Record<string, ParamValue>;
  summary: { level: Level; errors: number; warnings: number };
}

/** One aligned row of a side-by-side hunk; `a`/`b` are null when absent. */
export interface DiffRow {
  type: "equal" | "insert" | "delete" | "replace";
  a: string | null;
  b: string | null;
  a_no: number | null;
  b_no: number | null;
}

export interface Hunk {
  a_start: number | null;
  b_start: number | null;
  rows: DiffRow[];
}

export interface FileDiff {
  file: string;
  unified: string;
  hunks: Hunk[];
  byte_identical: boolean;
  added?: number;
  removed?: number;
}

export interface PreviewResult {
  diffs: FileDiff[];
  /** Param id -> refusal reason. Empty when every edit is acceptable. */
  validations: Record<string, string>;
  skipped: Record<string, string[]>;
  derived: Derived;
  params: Param[];
  changed_files: string[];
  is_noop: boolean;
}

export interface ApplyResult {
  diffs: FileDiff[];
  validations: Record<string, string>;
  written: { file: string; bytes: number }[];
  is_noop: boolean;
  derived: Derived;
  params: Param[];
  changed_files: string[];
}

export interface RevertResult {
  restored: string[];
  snapshot: { index: number; label: string; created: number; files: Record<string, number>; written: string[] };
  params: Param[];
  derived: Derived;
  stack: { index: number; label: string; created: number; files: Record<string, number>; written: string[] }[];
}

export interface CaseEntry {
  path: string;
  name: string;
  /** How many of the parameter rules this case matched, out of `total`. */
  recognized: number;
  total: number;
}

/** One subfolder in the folder browser's listing. */
export interface BrowseEntry {
  name: string;
  /** Repository-relative, which is what every other endpoint takes. */
  path: string;
  /** Holds a `CFD/system/controlDict`, so it can actually be opened. */
  is_case: boolean;
}

/** One level of the filesystem, as the folder browser sees it.
 *
 * Only the level asked for is listed -- the browser walks down one click at a
 * time -- so `parent` is how it goes back up, and is `null` only at a filesystem
 * root, where there is genuinely nothing above.  Nothing here decides what may be
 * opened: a picked path goes through the same `selectCase` call a hand-typed one
 * does, so the backend still has the last word.
 */
export interface BrowseListing {
  repo: string;
  /** Repository-relative while inside it, absolute once outside; `""` at the
      repository root. */
  path: string;
  /** Whether `path` is still inside the repository, which is what decides if the
      trail starts at the repository or needs it offered as a way back. */
  inside_repo: boolean;
  /** Every level from the anchor down to here, ready to render. */
  crumbs: { label: string; path: string }[];
  name: string;
  parent: string | null;
  /** Whether *this* directory is a case, i.e. whether it can be picked. */
  is_case: boolean;
  entries: BrowseEntry[];
}

/** One case file as the in-dashboard editor sees it.
 *
 * `text` is LF-only, because that is what a textarea round-trips; `eol` is the
 * convention the file itself uses.  Keeping the two apart is what lets a CRLF
 * dictionary be opened and saved without every line being rewritten. */
export interface CaseFile {
  file: string;
  text: string;
  eol: "crlf" | "lf";
  bytes: number;
  /** Of the bytes as they are on disk, so a stale editor cannot clobber them. */
  sha: string;
}

export interface SavedFile {
  file: string;
  is_noop: boolean;
  bytes: number;
  sha: string;
}

/** An edit is only ever `{id, value, enabled?}`: the backend owns all file
    knowledge.  `enabled` is sent for a toggle param whose live/commented-out
    state was flipped, independently of whether the value also changed. */
export interface Edit {
  id: string;
  value: ParamValue;
  enabled?: boolean;
}
