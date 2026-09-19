import { useMemo, useState, type DragEvent } from "react";
import {
  changedEdits,
  orderedChecks,
  orderedMetrics,
  useStore,
  type CardSection,
} from "./store";
import { Translator } from "./i18n";
import type { Consistency, Edit, Metric, Param } from "./types";

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

/** Metrics in the order the panel shows them: the arrangement the user dragged
 * into place, with the backend's order filling in the rest. */
export function useOrderedMetrics(): Metric[] {
  const derived = useStore((s) => s.derived);
  const order = useStore((s) => s.cardOrder.metrics);
  return useMemo(() => orderedMetrics(derived, order), [derived, order]);
}

/** Findings in the order the panel shows them: severity first, the user's
 * arrangement inside each level.  `ConsistencyList` used to sort severity
 * itself; that rule now lives in `orderedChecks` so a drag can reason about
 * the same list it is rearranging. */
export function useOrderedChecks(): Consistency[] {
  const derived = useStore((s) => s.derived);
  const order = useStore((s) => s.cardOrder.checks);
  return useMemo(() => orderedChecks(derived, order), [derived, order]);
}

/** Everything a card list needs to drag its cards into order. */
export interface CardDrag {
  /** The card in flight, or null when nothing is being dragged. */
  dragging: string | null;
  /** Where the insertion line goes, or null when there is none. */
  over: { id: string; above: boolean } | null;
  start: (id: string, e: DragEvent<HTMLElement>) => void;
  end: () => void;
  enter: (id: string, above: boolean) => void;
  drop: (id: string, above: boolean) => void;
}

/**
 * Native HTML5 drag-and-drop for one section's cards.
 *
 * One instance per section, and each instance only ever paints the cards it
 * owns.  That boundary is the whole defence against a metric being dropped
 * into the findings: the other section's `dragging` is still null, so its
 * cards draw no insertion line and its `dragover` never calls
 * `preventDefault` -- which is exactly what the browser reads as "not a drop
 * target".  Nothing else checks the section.
 *
 * No pointer-event fallback: this is a local desktop page on 127.0.0.1, and
 * native DnD is the only form of it that needs no dependency.
 */
export function useCardDrag(section: CardSection): CardDrag {
  const moveCard = useStore((s) => s.moveCard);
  const [dragging, setDragging] = useState<string | null>(null);
  const [over, setOver] = useState<{ id: string; above: boolean } | null>(null);

  return {
    dragging,
    over,

    start: (id, e) => {
      setDragging(id);
      // Firefox refuses to start a drag when no data was set.
      e.dataTransfer.setData("text/plain", id);
      e.dataTransfer.effectAllowed = "move";
      // The default drag image is whatever is under the cursor -- a 12px dot
      // grid.  Drag the whole card instead, grabbed near its top-left.
      const card = (e.currentTarget as HTMLElement).closest("[data-card-id]");
      if (card) e.dataTransfer.setDragImage(card, 20, 12);
    },

    // Unconditional: a drop on empty space fires no `drop` at all, so this is
    // the only thing that resets a drag that ended nowhere.  Without it
    // `dragging` sticks and every later drag is silently dead.
    end: () => {
      setDragging(null);
      setOver(null);
    },

    enter: (id, above) => {
      if (dragging === null) return;
      // A card is its own drop target; a line on the one already under the
      // cursor is only a flicker.
      const want = id === dragging ? null : { id, above };
      // `dragover` fires at ~60Hz.  Returning the identical object lets React
      // bail out of the re-render, which matters here: every card carries a
      // `backdrop-filter`, and repainting the column every frame is precisely
      // what not to do.
      setOver((prev) => {
        if (want === null) return prev === null ? prev : null;
        return prev?.id === want.id && prev.above === want.above ? prev : want;
      });
    },

    drop: (id, above) => {
      if (dragging === null) return;
      moveCard(section, dragging, id, above);
      setDragging(null);
      setOver(null);
    },
  };
}
