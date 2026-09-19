import { useMemo } from "react";
import { changedEdits, useStore } from "./store";
import { Translator } from "./i18n";
import type { Edit, Param } from "./types";

/**
 * The translator for the current language.  Components subscribe to `lang`, so
 * switching it re-renders every one of them -- which is what makes the labels
 * the backend supplied (known only by id) change along with the panel's own
 * text.
 */
export function useT(): Translator {
  const lang = useStore((s) => s.lang);
  return useMemo(() => new Translator(lang), [lang]);
}

/**
 * zustand v5 runs selectors through `useSyncExternalStore`, which compares by
 * identity -- a selector that builds a fresh array every call re-renders
 * forever.  So raw slices are selected and the derived shape is memoised here.
 */
export function useLiveEdits(): Edit[] {
  const payload = useStore((s) => s.payload);
  const edits = useStore((s) => s.edits);
  const toggles = useStore((s) => s.toggles);
  return useMemo(
    () => changedEdits(payload, edits, toggles),
    [payload, edits, toggles],
  );
}

export function useParamsByGroup(groupId: string): Param[] {
  const payload = useStore((s) => s.payload);
  return useMemo(() => {
    const group = payload?.groups.find((g) => g.id === groupId);
    if (!group || !payload) return [];
    const byId = new Map(payload.params.map((p) => [p.id, p]));
    return group.param_ids.map((id) => byId.get(id)).filter((p): p is Param => !!p);
  }, [payload, groupId]);
}

/**
 * Which params each consistency finding touches, by severity.  A param can
 * appear in several findings; the worse level wins.
 */
export function useIssueMap(): Record<string, "warn" | "error"> {
  const consistency = useStore((s) => s.derived?.consistency);
  return useMemo(() => {
    const out: Record<string, "warn" | "error"> = {};
    for (const c of consistency ?? []) {
      if (c.level !== "warn" && c.level !== "error") continue;
      for (const pid of c.param_ids) {
        if (out[pid] === "error") continue;
        out[pid] = c.level;
      }
    }
    return out;
  }, [consistency]);
}

/** Group-level rollup so a tab can show a warning dot without opening it. */
export function useGroupLevels(): Record<string, "warn" | "error"> {
  const payload = useStore((s) => s.payload);
  const consistency = useStore((s) => s.derived?.consistency);
  return useMemo(() => {
    const out: Record<string, "warn" | "error"> = {};
    if (!payload) return out;
    const groupOf = new Map(payload.params.map((p) => [p.id, p.group]));
    for (const c of consistency ?? []) {
      if (c.level !== "warn" && c.level !== "error") continue;
      for (const pid of c.param_ids) {
        const g = groupOf.get(pid);
        if (!g) continue;
        if (out[g] === "error") continue;
        out[g] = c.level;
      }
    }
    return out;
  }, [payload, consistency]);
}
