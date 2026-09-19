import { create } from "zustand";
import { ApiError, api, setApiLang } from "./api";
import { Translator, pickLang, type Lang } from "./i18n";
import { LEVEL_RANK } from "./format";
import type {
  ApplyResult,
  CaseEntry,
  CasePayload,
  Consistency,
  Derived,
  Edit,
  Metric,
  ParamValue,
  PreviewResult,
} from "./types";

export type ToastKind = "ok" | "error" | "warn" | "info";

export interface Toast {
  id: number;
  kind: ToastKind;
  /** Already translated: a toast outlives the language it was raised in. */
  text: string;
  detail?: string;
}

/** Where the chosen language is remembered between visits. */
const LANG_KEY = "dash.lang";

const initialLang = pickLang(readStoredLang());

function readStoredLang(): string | null {
  try {
    return window.localStorage.getItem(LANG_KEY);
  } catch {
    return null;
  }
}

/** The two looks the panel ships with.  ``default`` is the dark liquid glass
 * the panel has always had; ``light`` is the same glass on a light backdrop.
 * The name of the first one says "unchanged", not "plain" -- it is what a
 * visit starts on and what a browser with no stored choice gets. */
export type Theme = "default" | "light";

/** Where the chosen style is remembered between visits. */
const THEME_KEY = "dash.theme";

const initialTheme = pickTheme(readStoredTheme());

function readStoredTheme(): string | null {
  try {
    return window.localStorage.getItem(THEME_KEY);
  } catch {
    return null;
  }
}

/** Only ``light`` is a real choice; anything else (including a stale key from a
 * future style) falls back to ``default`` rather than rendering an unknown
 * theme attribute. */
export function pickTheme(raw: string | null | undefined): Theme {
  return raw === "light" ? "light" : "default";
}

/** The two card lists in the derived panel that can be dragged into order.
 * They are remembered separately: a metric is not a finding, and dropping one
 * onto the other means nothing. */
export type CardSection = "metrics" | "checks";

/** Where the dragged card order is remembered between visits. */
const CARD_ORDER_KEY = "dash.cardOrder";

function emptyOrder(): Record<CardSection, string[]> {
  return { metrics: [], checks: [] };
}

const initialCardOrder = readStoredOrder();

/**
 * One key holds both sections, so a value that is not shaped like a card order
 * is replaced whole rather than patched: a half-readable value is worse than
 * no memory at all, which is exactly the backend's own order.
 */
function readStoredOrder(): Record<CardSection, string[]> {
  try {
    const raw = window.localStorage.getItem(CARD_ORDER_KEY);
    if (!raw) return emptyOrder();
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return emptyOrder();
    const src = parsed as Record<string, unknown>;
    return { metrics: idList(src.metrics), checks: idList(src.checks) };
  } catch {
    return emptyOrder();
  }
}

function idList(raw: unknown): string[] {
  return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === "string") : [];
}

/**
 * Persist the order.  This is called from a drop handler, so a `setItem` that
 * throws (private mode) must not escape as an uncaught error on the way out of
 * a React event.
 */
function setCardOrderEffects(order: Record<CardSection, string[]>): void {
  try {
    window.localStorage.setItem(CARD_ORDER_KEY, JSON.stringify(order));
  } catch {
    /* private mode: the arrangement just does not outlive the tab */
  }
}

/**
 * Reorder `items` to match a remembered `order`, without ever pruning the
 * memory.
 *
 * A card can come and go as the inputs change -- `derived.py` appends several
 * of them conditionally -- so `order` routinely names cards that are not here
 * right now, and `items` routinely holds cards `order` has never heard of.
 * Both are legal, and both are handled without touching `order`:
 *
 * * An id in `order` sorts by its position there.
 * * An id that is not follows whichever id *before it in `items`* is in
 *   `order`; with no such predecessor it goes to the front.  Following the
 *   backend neighbour rather than falling to the end is what makes a card that
 *   disappeared and came back land near where it was.
 * * Nothing is ever dropped from `order`: an id missing today may be back
 *   tomorrow, and forgetting it would silently reset that part of the
 *   arrangement.  Do not "tidy up" the stale ids.
 *
 * An empty `order` means "never arranged", i.e. the backend's own order, and
 * is returned untouched.
 */
export function applyCardOrder<T>(
  items: T[],
  order: string[],
  id: (x: T) => string,
): T[] {
  if (!order.length) return items;
  const place = new Map(order.map((x, i) => [x, i]));
  let last = -1;
  const keyed = items.map((item) => {
    const at = place.get(id(item));
    if (at !== undefined) last = at;
    return { item, key: last };
  });
  // Stable (ES2019), so equal keys -- every card the user has never moved --
  // keep the backend's relative order.
  keyed.sort((a, b) => a.key - b.key);
  return keyed.map((k) => k.item);
}

/** The metric list as the panel shows it.  The All / Issues filter is applied
 * by the caller *after* this, so order and filtering never fight. */
export function orderedMetrics(derived: Derived | null, order: string[]): Metric[] {
  return applyCardOrder(derived?.metrics ?? [], order, (m) => m.id);
}

/** The finding list as the panel shows it: the remembered arrangement, then
 * severity.  Severity has the last word, so a stored order can never lift a
 * warning above an error -- the sort is stable, so the manual arrangement
 * survives inside a level. */
export function orderedChecks(derived: Derived | null, order: string[]): Consistency[] {
  const arranged = applyCardOrder(derived?.consistency ?? [], order, (c) => c.id);
  return [...arranged].sort((a, b) => LEVEL_RANK[a.level] - LEVEL_RANK[b.level]);
}

/** A case file held open in the panel's editor.
 *
 * `saved` is what came off disk, so `text !== saved` is exactly "there is
 * something to write", and `sha` is what the backend compares against to make
 * sure a parameter write did not land in between. */
export interface EditorSession {
  file: string;
  saved: string;
  text: string;
  eol: "crlf" | "lf";
  sha: string;
}

/** Numeric comparison so `0.1` typed by hand equals `0.1` read from the file. */
export function valuesEqual(a: ParamValue, b: ParamValue): boolean {
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b)) return false;
    return a.length === b.length && a.every((x, i) => numEq(x, b[i]));
  }
  if (typeof a === "number" && typeof b === "number") return numEq(a, b);
  if (typeof a === "boolean" || typeof b === "boolean") return a === b;
  return String(a ?? "") === String(b ?? "");
}

function numEq(a: unknown, b: unknown): boolean {
  const x = typeof a === "number" ? a : Number(a);
  const y = typeof b === "number" ? b : Number(b);
  if (Number.isNaN(x) || Number.isNaN(y)) return String(a) === String(b);
  return Math.abs(x - y) <= 1e-12 * Math.max(1, Math.abs(x), Math.abs(y));
}

interface State {
  // -- environment --
  cases: CaseEntry[];
  repo: string;

  // -- case --
  casePath: string | null;
  payload: CasePayload | null;
  /** Only params the user has touched; the backend re-reads the files itself. */
  edits: Record<string, ParamValue>;
  /** Pending on/off state for toggle params, keyed by id. */
  toggles: Record<string, boolean>;
  derived: Derived | null;
  /** Cards of the derived panel whose content the last *live* recompute
      changed, each under a counter that advances every time it changes: a card
      replays its highlight by keying an overlay on its own number.  Empty until
      the first edit -- see `changedCards`. */
  flashes: Record<string, number>;
  preview: PreviewResult | null;
  lastApply: ApplyResult | null;

  // -- ui --
  lang: Lang;
  theme: Theme;
  loading: boolean;
  busy: boolean;
  diffOpen: boolean;
  /** The file open in the panel's own editor, if any. */
  editor: EditorSession | null;
  /** Revert overwrites files without a diff, so it asks first. */
  revertConfirm: boolean;
  toasts: Toast[];
  /** Card ids the user has dragged into place, per section; see
   * `applyCardOrder` for how the rest of each list is placed around them. */
  cardOrder: Record<CardSection, string[]>;
  /** Set by the derived panel so a click can scroll to & flash a field. */
  focusParam: string | null;
  /** Bumped on every focus request, so a re-click still counts as one. */
  focusSeq: number;

  // -- actions --
  setLang: (lang: Lang) => Promise<void>;
  setTheme: (theme: Theme) => void;
  boot: () => Promise<void>;
  /** Resolves `true` once the case is loaded; `false` leaves the open case alone. */
  selectCase: (path: string) => Promise<boolean>;
  setEdit: (id: string, value: ParamValue) => void;
  setToggle: (id: string, enabled: boolean) => void;
  clearEdit: (id: string) => void;
  resetAll: () => void;
  /** Open a case file in the panel, for a parameter we cannot place. */
  openFile: (file: string) => Promise<void>;
  setEditorText: (text: string) => void;
  saveFile: () => Promise<void>;
  closeEditor: () => void;
  /** Re-read the open case from disk, keeping whatever is still unwritten. */
  reload: () => Promise<void>;
  openDiff: () => Promise<void>;
  closeDiff: () => void;
  apply: () => Promise<void>;
  requestRevert: () => void;
  cancelRevert: () => void;
  revert: () => Promise<void>;
  toast: (kind: ToastKind, text: string, detail?: string) => void;
  dismissToast: (id: number) => void;
  /** Move a card next to another within its own section.  A move that the
   * display rules would immediately undo is dropped rather than stored. */
  moveCard: (section: CardSection, id: string, target: string, above: boolean) => void;
  resetCardOrder: (section: CardSection) => void;
  setFocusParam: (id: string | null) => void;
}

let toastSeq = 0;
let deriveTimer: number | undefined;

/**
 * Strip no-op edits: only genuinely different values ever reach the backend.
 *
 * A toggle param may change by flipping its line on or off alone, so the ids
 * come from both maps and such a param stays eligible while it is disabled --
 * that is the only way to switch it back on.
 */
/** The translate function for an action, which reads `lang` at call time. */
const tr = (lang: Lang) => new Translator(lang);

/** Everything outside React that follows the language: tab, `<html lang>`, disk. */
function setLangEffects(lang: Lang): void {
  document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  document.title = tr(lang).t("CFDEMInterFoamIB · Case dashboard");
  try {
    window.localStorage.setItem(LANG_KEY, lang);
  } catch {
    /* private mode: the choice just does not outlive the tab */
  }
}

/** The one thing outside React that follows the style: `<html data-theme>`,
 * which is what every colour in `index.css` hangs off.  No re-fetch here, so
 * unlike `setLang` this is a synchronous swap -- the theme is pure CSS.
 *
 * ``colorScheme`` is set as well as the attribute: it is what tells the browser
 * to draw its own furniture -- scrollbars, the caret, autofill -- for the
 * backdrop, and CSS `color-scheme` alone loses that race on a cold load. */
function setThemeEffects(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme === "light" ? "light" : "dark";
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* private mode: the choice just does not outlive the tab */
  }
}

export function changedEdits(  payload: CasePayload | null,
  edits: Record<string, ParamValue>,
  toggles: Record<string, boolean>,
): Edit[] {
  if (!payload) return [];
  const byId = new Map(payload.params.map((p) => [p.id, p]));
  const out: Edit[] = [];
  for (const id of new Set([...Object.keys(edits), ...Object.keys(toggles)])) {
    const param = byId.get(id);
    if (!param || (!param.editable && !param.toggle)) continue;
    const value = edits[id] !== undefined ? edits[id] : param.value;
    const on = toggles[id];
    const flip = param.toggle && on !== undefined && on !== param.enabled;
    if (!flip && valuesEqual(value, param.value)) continue;
    out.push({ id, value: value as Edit["value"], ...(flip ? { enabled: on } : {}) });
  }
  return out;
}

/**
 * 150 ms debounce: recompute warnings while typing, not on every keystroke.
 * Reads the store through the hook so `setEdit` and `setToggle` can share it
 * without threading `set`/`get` through a helper.
 */
function deriveSoon() {
  if (deriveTimer !== undefined) window.clearTimeout(deriveTimer);
  deriveTimer = window.setTimeout(async () => {
    const { casePath, payload, edits, toggles, derived: before } = useStore.getState();
    if (!casePath) return;
    try {
      const next = await api.derive(casePath, changedEdits(payload, edits, toggles));
      const flashes = { ...useStore.getState().flashes };
      for (const key of changedCards(before, next)) flashes[key] = (flashes[key] ?? 0) + 1;
      useStore.setState({ derived: next, flashes });
    } catch {
      /* a stale derive is not worth interrupting the user for */
    }
  }, 150);
}

/**
 * The key a derived-panel card is filed under.  Metrics and findings share one
 * map but not one namespace, and their ids are not apart already -- the
 * submerged-particle metric and finding are both `dem.submerged`.
 */
export function flashKey(kind: "metric" | "check", id: string): string {
  return `${kind}:${id}`;
}

/** Everything one card shows, so that any change to any of it reads as "this
    card updated" -- including one that only alters the wording.  A metric's
    value is the pair `display`/`detail`; a finding's is its `level`/`title`. */
function cardSignature(c: Metric | Consistency): string {
  const shown = "display" in c ? [c.display, c.detail] : [c.level, c.title];
  const refs = "sources" in c ? c.sources : c.source_refs;
  return JSON.stringify([...shown, c.message, refs.map((r) => String(r.value))]);
}

/**
 * Which derived-panel cards a fresh result actually changed, so that those --
 * and only those -- can light up.  A card that has just appeared counts: a
 * finding surfacing is the one arrival worth looking up for.
 *
 * Only the live path calls this.  Opening a case, switching language, rolling
 * back or previewing all replace the panel wholesale, and lighting up every
 * card would say nothing about what the edit did.
 */
function changedCards(before: Derived | null, after: Derived): string[] {
  if (!before) return [];
  const prev = new Map<string, string>();
  for (const m of before.metrics) prev.set(flashKey("metric", m.id), cardSignature(m));
  for (const c of before.consistency) prev.set(flashKey("check", c.id), cardSignature(c));
  const out: string[] = [];
  for (const m of after.metrics) {
    const key = flashKey("metric", m.id);
    if (prev.get(key) !== cardSignature(m)) out.push(key);
  }
  for (const c of after.consistency) {
    const key = flashKey("check", c.id);
    if (prev.get(key) !== cardSignature(c)) out.push(key);
  }
  return out;
}

export const useStore = create<State>()((set, get) => ({
  cases: [],
  repo: "",
  casePath: null,
  payload: null,
  edits: {},
  toggles: {},
  derived: null,
  flashes: {},
  preview: null,
  lastApply: null,
  lang: initialLang,
  theme: initialTheme,
  loading: false,
  busy: false,
  diffOpen: false,
  editor: null,
  revertConfirm: false,
  toasts: [],
  cardOrder: initialCardOrder,
  focusParam: null,
  focusSeq: 0,

  /**
   * Switching language re-reads the case rather than only re-rendering.
   *
   * The panel's own text is translated in the browser, but the parameter names
   * and file card names arrive *inside* the payload the backend sent, and the
   * consistency findings inside the derived result.  So the payload and the
   * derive have to be fetched again for those to change at all; `reload` is
   * exactly that, and it keeps whatever is still unwritten.
   */
  setLang: async (lang) => {
    if (lang === get().lang) return;
    set({ lang, toasts: [] });
    setApiLang(lang);
    setLangEffects(lang);
    if (!get().casePath) return;
    const reopen = !!get().preview;
    await get().reload();
    if (reopen) await get().openDiff();
  },

  /**
   * Switching style is a CSS-only swap: every colour is a custom property on
   * the root, so setting `data-theme` repaints the whole panel with no fetch
   * and no re-render of the payload.
   */
  setTheme: (theme) => {
    if (theme === get().theme) return;
    set({ theme });
    setThemeEffects(theme);
  },

  boot: async () => {
    set({ loading: true });
    try {
      const listing = await api.cases();
      set({ cases: listing.cases, repo: listing.repo });
      const first = get().casePath ?? listing.cases[0]?.path ?? null;
      if (first) await get().selectCase(first);
    } catch (exc) {
      get().toast("error", tr(get().lang).t("Start-up failed"), (exc as Error).message);
    } finally {
      set({ loading: false });
    }
  },

  selectCase: async (path: string) => {
    set({ loading: true });
    try {
      const payload = await api.case(path);
      // The payload carries the canonical repo-relative path; use it so a
      // hand-typed `tutorial\single_sphere` or an absolute path ends up as the
      // same string the case list uses.
      const canonical = payload.path;
      // Clear the pending edits only *after* the new case loaded.  A failed
      // switch must not discard the unwritten edits, and must not blank out the
      // case that is still open -- a mistyped path is not a reason to close it.
      set({
        casePath: canonical,
        payload,
        derived: null,
        preview: null,
        lastApply: null,
        edits: {},
        toggles: {},
      });
      set({ derived: await api.derive(canonical, []) });
      return true;
    } catch (exc) {
      if (!get().payload) set({ payload: null, casePath: null });
      get().toast("error", tr(get().lang).t("Could not open the case"), (exc as Error).message);
      return false;
    } finally {
      set({ loading: false });
    }
  },

  setEdit: (id, value) => {
    set((s) => ({ edits: { ...s.edits, [id]: value }, preview: null }));
    deriveSoon();
  },

  setToggle: (id, enabled) => {
    set((s) => ({ toggles: { ...s.toggles, [id]: enabled }, preview: null }));
    deriveSoon();
  },

  clearEdit: (id) => {
    set((s) => {
      const edits = { ...s.edits };
      const toggles = { ...s.toggles };
      delete edits[id];
      delete toggles[id];
      return { edits, toggles, preview: null };
    });
  },

  resetAll: () => {
    set({ edits: {}, toggles: {}, preview: null });
    const { casePath } = get();
    if (casePath) void api.derive(casePath, []).then((d) => set({ derived: d }));
  },

  openFile: async (file) => {
    const { casePath } = get();
    if (!casePath) return;
    set({ busy: true });
    try {
      const f = await api.file(casePath, file);
      set({
        editor: { file: f.file, saved: f.text, text: f.text, eol: f.eol, sha: f.sha },
      });
    } catch (exc) {
      get().toast("error", tr(get().lang).t("Could not open the file"), (exc as Error).message);
    } finally {
      set({ busy: false });
    }
  },

  setEditorText: (text) =>
    set((s) => (s.editor ? { editor: { ...s.editor, text } } : {})),

  saveFile: async () => {
    const { casePath, editor } = get();
    if (!casePath || !editor) return;
    set({ busy: true });
    try {
      const saved = await api.saveFile(casePath, editor.file, editor.text, editor.sha);
      set({ editor: null });
      const t = tr(get().lang);
      get().toast(
        saved.is_noop ? "info" : "ok",
        saved.is_noop ? t.t("No change") : t.t("Wrote {file}", { file: editor.file }),
        saved.is_noop
          ? t.t("Byte-identical to the file on disk; nothing changed.")
          : t.t("Undo it with Roll back in the top bar."),
      );
      // The whole point of the edit is usually a line the rules could not find,
      // so re-read straight away and let it show up as recognized.
      await get().reload();
    } catch (exc) {
      const t = tr(get().lang);
      get().toast(
        "error",
        t.t("Write failed"),
        exc instanceof ApiError && exc.status === 409
          ? t.t("{file} changed after it was opened; close it and reopen to edit.", {
              file: editor.file,
            })
          : (exc as Error).message,
      );
    } finally {
      set({ busy: false });
    }
  },

  closeEditor: () => set({ editor: null }),

  reload: async () => {
    const { casePath } = get();
    if (!casePath) return;
    set({ loading: true });
    try {
      const payload = await api.case(casePath);
      // Unwritten edits survive: the file changed underneath them, but throwing
      // away what the user typed is not what this button is for.
      set({ payload, preview: null });
      const { edits, toggles } = get();
      set({ derived: await api.derive(casePath, changedEdits(payload, edits, toggles)) });
    } catch (exc) {
      get().toast("error", tr(get().lang).t("Re-read failed"), (exc as Error).message);
    } finally {
      set({ loading: false });
    }
  },

  openDiff: async () => {
    const { casePath, payload, edits, toggles } = get();
    if (!casePath) return;
    const live = changedEdits(payload, edits, toggles);
    if (!live.length) {
      const t = tr(get().lang);
      get().toast("info", t.t("Nothing to change"), t.t("Change at least one parameter before previewing."));
      return;
    }
    set({ busy: true });
    try {
      const preview = await api.preview(casePath, live);
      set({ preview, derived: preview.derived, diffOpen: true });
    } catch (exc) {
      get().toast("error", tr(get().lang).t("Preview failed"), (exc as Error).message);
    } finally {
      set({ busy: false });
    }
  },

  closeDiff: () => set({ diffOpen: false }),

  apply: async () => {
    const { casePath, payload, edits, toggles } = get();
    if (!casePath) return;
    const live = changedEdits(payload, edits, toggles);
    if (!live.length) {
      const t = tr(get().lang);
      get().toast("info", t.t("Nothing to change"), t.t("There is nothing to write."));
      return;
    }
    set({ busy: true });
    try {
      const result = await api.apply(casePath, live);
      set({
        lastApply: result,
        preview: null,
        diffOpen: false,
        edits: {},
        toggles: {},
        derived: result.derived,
      });
      // Re-read so every field shows the value that actually landed on disk.
      const payloadAfter = await api.case(casePath);
      set({ payload: payloadAfter });
      const t = tr(get().lang);
      if (result.is_noop) {
        get().toast("info", t.t("No change"), t.t("The content matches the files on disk; no bytes were changed."));
      } else {
        get().toast(
          "ok",
          t.t("Wrote {n} files", { n: result.changed_files.length }),
          result.changed_files.join("\n"),
        );
      }
      const refused = Object.entries(result.validations ?? {});
      if (refused.length) {
        get().toast(
          "warn",
          t.t("{n} changes refused", { n: refused.length }),
          refused.map(([id, why]) => `${id}: ${why}`).join("\n"),
        );
      }
    } catch (exc) {
      const t = tr(get().lang);
      const detail =
        exc instanceof ApiError && exc.status === 409
          ? t.t("The case is being written; try again in a moment.")
          : (exc as Error).message;
      get().toast("error", t.t("Write failed"), detail);
    } finally {
      set({ busy: false });
    }
  },

  requestRevert: () => set({ revertConfirm: true }),
  cancelRevert: () => set({ revertConfirm: false }),

  revert: async () => {
    const { casePath } = get();
    if (!casePath) return;
    set({ busy: true, revertConfirm: false });
    try {
      const result = await api.revert(casePath);
      set({ derived: result.derived, edits: {}, toggles: {}, preview: null, diffOpen: false });
      const payloadAfter = await api.case(casePath);
      set({ payload: payloadAfter });
      const t = tr(get().lang);
      get().toast("ok", t.t("Rolled back {n} files", { n: result.restored.length }), result.restored.join("\n"));
    } catch (exc) {
      const t = tr(get().lang);
      const detail =
        exc instanceof ApiError && exc.status === 409
          ? t.t("There is no snapshot to roll back to.")
          : (exc as Error).message;
      get().toast(exc instanceof ApiError && exc.status === 409 ? "info" : "error", t.t("Roll back failed"), detail);
    } finally {
      set({ busy: false });
    }
  },

  toast: (kind, text, detail) => {
    const id = ++toastSeq;
    set((s) => ({ toasts: [...s.toasts, { id, kind, text, detail }] }));
    window.setTimeout(
      () => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
      kind === "error" ? 9000 : 4200,
    );
  },

  dismissToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  moveCard: (section, id, target, above) => {
    if (id === target) return;
    const { derived, cardOrder } = get();

    // The list the user is looking at: unfiltered, and in display order.  The
    // stored order is meant to be exactly this, so a legal drag round-trips
    // through the severity sort unchanged on the next read.
    const display = (order: string[]): string[] =>
      section === "metrics"
        ? orderedMetrics(derived, order).map((m) => m.id)
        : orderedChecks(derived, order).map((c) => c.id);

    const items = display(cardOrder[section]);
    // One guard covers both ways a target can be wrong: the card the drag
    // started on has been re-derived away in the meantime, or the id and the
    // target are not even in the same section.
    if (!items.includes(id) || !items.includes(target)) return;

    const next = items.filter((x) => x !== id);
    next.splice(next.indexOf(target) + (above ? 0 : 1), 0, id);

    // A drag across a severity boundary sorts straight back, so nothing the
    // user can see has changed.  That is not an arrangement; remembering it
    // would pin a warning under a rule it never appeared to obey, and spring
    // it the next time a finding in between changes level.
    if (display(next).every((x, i) => x === items[i])) return;

    const order = { ...cardOrder, [section]: next };
    set({ cardOrder: order });
    setCardOrderEffects(order);
  },

  resetCardOrder: (section) => {
    const order = { ...get().cardOrder, [section]: [] };
    set({ cardOrder: order });
    // Not `removeItem`: the one key holds both sections, so dropping it would
    // take the other section's arrangement down with it.
    setCardOrderEffects(order);
  },

  setFocusParam: (id) =>
    set((s) => ({ focusParam: id, focusSeq: s.focusSeq + 1 })),
}));

// Derived views over (payload, edits) live in hooks.ts: a selector that builds
// a new array each call would re-render forever under zustand v5.

// Apply the remembered language to the document before the first render, so a
// Chinese session does not start on an English `<title>` and `<html lang>`.
setLangEffects(initialLang);

// Same for the style, and for the same reason: the attribute has to be on
// `<html>` before the first paint or a light session flashes dark.
setThemeEffects(initialTheme);

