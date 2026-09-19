import type { DragEvent, ReactNode } from "react";
import type { CardDrag } from "../hooks";
import type { CardSection } from "../store";

/**
 * A drop target wrapped around one card: it owns the insertion line and the
 * dimmed look of the card being dragged away from here.
 *
 * The wrapper, not the card, is what answers `dragover` and `drop`, so the
 * whole card is a target while every click target inside it stays untouched.
 *
 * It lives in its own module because both lists use it: importing it from
 * either one would make `DerivedPanel` and `ConsistencyList` import each
 * other.
 *
 * The `key` goes on this element rather than on the card, so a drop moves the
 * card instead of remounting it -- which would otherwise throw away whatever
 * the card remembers, such as a finding's expanded state.
 */
export function CardSlot({
  id,
  drag,
  section,
  children,
}: {
  id: string;
  drag: CardDrag;
  section: CardSection;
  children: ReactNode;
}) {
  // Top half of the card means "insert before it", bottom half "after it".
  const above = (e: DragEvent<HTMLElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    return e.clientY < r.top + r.height / 2;
  };

  return (
    <div
      data-card-id={id}
      data-section={section}
      className={`relative ${drag.dragging === id ? "opacity-40" : ""}`}
      onDragOver={(e) => {
        // No `preventDefault` when nothing is being dragged: that is exactly
        // what makes the browser refuse a card dragged in from the other
        // section, which has its own `useCardDrag` and so is still idle.
        if (drag.dragging === null) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        drag.enter(id, above(e));
      }}
      onDrop={(e) => {
        e.preventDefault();
        drag.drop(id, above(e));
      }}
    >
      {drag.over?.id === id && (
        <span
          className={`pointer-events-none absolute left-0 right-0 h-0.5 rounded bg-accent ${
            drag.over.above ? "-top-[3px]" : "-bottom-[3px]"
          }`}
        />
      )}
      {children}
    </div>
  );
}
