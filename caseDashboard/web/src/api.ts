import { Translator, pickLang, type Lang } from "./i18n";
import type {
  ApplyResult,
  BrowseListing,
  CaseEntry,
  CaseFile,
  CasePayload,
  Derived,
  Edit,
  PreviewResult,
  RevertResult,
  SavedFile,
} from "./types";

/** Relative so the Vite proxy (dev) and the Python static host (prod) agree. */
const BASE = "/api";

/**
 * The panel's language, kept here so the few messages that are raised outside
 * React -- a failed fetch, which happens before any component sees it -- are
 * wording-consistent with the rest.  `store.setLang` is what sets it.
 */
let translator = new Translator(pickLang(null));

export function setApiLang(lang: Lang): void {
  translator = new Translator(lang);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (exc) {
    throw new ApiError(
      0,
      translator.t("Cannot reach the backend: {message}", {
        message: (exc as Error).message,
      }),
    );
  }
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      throw new ApiError(res.status, text.slice(0, 400));
    }
  }
  if (!res.ok) {
    const msg =
      body && typeof body === "object" && "error" in body
        ? String((body as { error: unknown }).error)
        : `HTTP ${res.status}`;
    throw new ApiError(res.status, msg);
  }
  return body as T;
}

const q = (params: Record<string, string>) =>
  "?" + new URLSearchParams(params).toString();

export const api = {
  cases: () =>
    request<{ cases: CaseEntry[]; repo: string }>("/cases"),

  case: (path: string) => request<CasePayload>(`/case${q({ path })}`),

  preview: (path: string, edits: Edit[]) =>
    request<PreviewResult>("/case/preview", {
      method: "POST",
      body: JSON.stringify({ path, edits }),
    }),

  apply: (path: string, edits: Edit[]) =>
    request<ApplyResult>("/case/apply", {
      method: "POST",
      body: JSON.stringify({ path, edits }),
    }),

  revert: (path: string) =>
    request<RevertResult>("/case/revert", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),

  derive: (path: string, edits: Edit[]) =>
    request<Derived>("/case/derive", {
      method: "POST",
      body: JSON.stringify({ path, edits }),
    }),

  /** The text of one case file, so a line the parameter list has no rule for
      can be added by hand in the dashboard rather than in another program. */
  file: (path: string, file: string) =>
    request<CaseFile>(`/file${q({ path, file })}`),

  saveFile: (path: string, file: string, text: string, sha: string) =>
    request<SavedFile>("/file/save", {
      method: "POST",
      body: JSON.stringify({ path, file, text, sha }),
    }),

  /** One level of the filesystem for the folder browser.  `path` is
      repository-relative while inside it, absolute once outside, `""` for the
      repository root.  Unlike the OS dialog this used to be, it answers
      immediately -- there is no process to wait on. */
  browse: (path: string) => request<BrowseListing>(`/browse${q({ path })}`),
};
