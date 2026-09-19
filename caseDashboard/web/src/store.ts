import { create } from "zustand";
import { ApiError, api, setApiLang } from "./api";
import { Translator, pickLang, type Lang } from "./i18n";
import type {
  ApplyResult,
  CaseEntry,
  CasePayload,
  Derived,
  Edit,
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
    const { casePath, payload, edits, toggles } = useStore.getState();
    if (!casePath) return;
    try {
      useStore.setState({
        derived: await api.derive(casePath, changedEdits(payload, edits, toggles)),
      });
    } catch {
      /* a stale derive is not worth interrupting the user for */
    }
  }, 150);
}

export const useStore = create<State>()((set, get) => ({
  cases: [],
  repo: "",
  casePath: null,
  payload: null,
  edits: {},
  toggles: {},
  derived: null,
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

