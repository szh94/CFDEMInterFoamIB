/**
 * The highlight a card of the derived panel wears for a moment when a live
 * recompute changed it -- the cursor is in a value box somewhere else in the
 * page, and this is what says which card moved because of it.
 *
 * Painted *over* the card rather than on it: the cards carry their own ring
 * and translucent fill, and both have to survive the flash.  It lives in its
 * own module because both lists use it, and importing one list from the other
 * would make `DerivedPanel` and `ConsistencyList` import each other.
 *
 * `token` is the element's `key`, so a second change -- including one that
 * arrives before the first fade has finished -- remounts this span and replays
 * the animation.  A boolean could not: the class would already be there, and
 * an animation that is already applied does not restart.
 */
export function Flash({ token }: { token: number | undefined }) {
  if (!token) return null;
  return (
    <span
      key={token}
      aria-hidden
      className="anim-flash pointer-events-none absolute inset-0 rounded-md"
    />
  );
}
