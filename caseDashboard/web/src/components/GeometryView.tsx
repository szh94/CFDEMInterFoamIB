import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useStore } from "../store";
import { useT } from "../hooks";
import { IconChevron, IconUndo } from "./Icons";
import type { Param, ParamValue } from "../types";

/**
 * A picture of the mesh the `blockMeshDict` rules read: the corner points and
 * the boundary faces, drawn from the same effective values the metrics compute
 * with -- so retyping a corner number or a domain extent moves the box as you
 * type, before anything is written.
 *
 * The particles the DEM block creates are drawn inside it, at the centre and
 * diameter the particle table gives them and in the mesh's own frame, so a
 * sphere that would start outside the box shows up here -- as a picture rather
 * than as a run that dies in `create_atoms`.
 *
 * Plain SVG rather than a 3D library: a `blockMeshDict` is a handful of corners
 * and quads, and what is wanted is a box to look at, not a scene to navigate.
 * The points are centred and scaled into a unit cube and the `viewBox` does the
 * rest of the scaling, so the picture is crisp at any panel width and nothing
 * has to be measured or resized.
 */

/** The corner the box opens at: shows all three extents of the mesh at once,
    where a flat elevation would show two. */
const YAW0 = -0.62;
const PITCH0 = 0.42;

/** One hue per patch, cycled.  Which patch a face belongs to is worth seeing,
    so the colours only have to tell them apart -- they mean nothing else. */
const HUES = ["#35c6d4", "#f0813c", "#8fb2ff", "#b98cf0", "#79d17e", "#e6c25a", "#e27aa6"];

type Point = [number, number, number];

/** The three dictionary axes, for the corner glyph: red / green / blue for
    x / y / z, the way a plotting tool draws them, so the letters need no
    key.  They are letters rather than a position -- the glyph says which way
    the case's axes point, nothing about where anything is. */
const AXES: { name: string; dir: Point; hue: string }[] = [
  { name: "x", dir: [1, 0, 0], hue: "#e0574a" },
  { name: "y", dir: [0, 1, 0], hue: "#79d17e" },
  { name: "z", dir: [0, 0, 1], hue: "#5aa9f0" },
];

/** The normal glyph: how far a face's arrow reaches out of it, and the size of
    its head.  In placed units, so it grows with the picture rather than being
    a fixed number of pixels -- it is an annotation, not a measurement. */
const ARROW = 0.16;
const HEAD_L = 0.065;
const HEAD_W = 0.0275;

/** The vertex label's size in placed units -- what the preview draws, where the
    picture is an annotation in its own right and wants a size that grows with
    it. */
const LABEL_UNITS = 0.095;

/** How far the ink of a vertex label reaches above the dot it names, in placed
    units: the label's own lift plus the height of its text, which for the
    preview's `LABEL_UNITS` comes to a little over half again its size.  A
    corner dot is the only thing drawn that has this above it, so it is the one
    allowance the frame's top edge has to make over its foot -- see `top` in the
    view.  A number of its own rather than a multiple of the label size: the
    frame's shape is what everything else is placed inside, so it cannot be made
    to depend on the measurement taken of it. */
const LABEL_TOP = 0.15;

/** The label's offset from the dot it names, as a multiple of the label's own
    size: to the right, and lifted by about half a line, so the number clears
    the dot at any size. */
const LABEL_DX = 0.79;
const LABEL_DY = -0.63;

/** The size the labels are drawn at on the page, in CSS pixels: the legend's
    own size, because the two are read together there.  A placed-unit number
    could not do it -- the same one comes out at a different size on screen for
    every case, a cube filling the frame at a smaller scale than a long thin
    column -- so the page measures the drawing and divides. */
const LABEL_PX = 17;

/** The initial water box -- the `setFieldsDict` region -- as a wireframe, in a
    hue of its own and dashed, so it cannot be read as one of the mesh's own
    edges.  Nothing in `HUES` is this blue. */
const WATER_HUE = "#2f8fe0";

/** The twelve edges of a box whose eight corners are numbered as three bits --
    `4` = x high, `2` = y high, `1` = z high.  Two corners sharing an edge differ
    in exactly one bit, which is what makes this list complete and short. */
const BOX_EDGES: [number, number][] = [
  [0, 1], [2, 3], [4, 5], [6, 7],
  [0, 2], [1, 3], [4, 6], [5, 7],
  [0, 4], [1, 5], [2, 6], [3, 7],
];

/** A particle, in the case's own units: the centre its `create_atoms` line
    names and the diameter its `set atom` line gives it. */
interface Sphere {
  c: Point;
  r: number;
}

/** An axis-aligned region of the case, in the case's own units: the initial
    water. */
interface Box {
  lo: Point;
  hi: Point;
}

interface Mesh {
  /** Positional: a corner the rules could not resolve stays in the list as
      `null`, so the face indices that refer to it do not shift. */
  points: (Point | null)[];
  /** Faces kept as the corner *indices* the table names, not as points: they
      have to be drawn from the very same placed corners the dots are, or the
      two pictures disagree by whatever `place` did. */
  faces: { patch: string; nodes: number[] }[];
  /** Every patch a face was found under, in the order they first appear. */
  patches: string[];
  /** The particles the DEM block creates, in the same frame as the corners. */
  spheres: Sphere[];
  /** The initial water, or `null` when the case writes no usable box. */
  water: Box | null;
}

/**
 * `stage` is the standalone picture the fluid page opens with; the sidebar
 * keeps the short `preview` of the same drawing.  One component, because it is
 * one drawing -- only the room it is given differs.
 */
export function GeometryView({ stage = false }: { stage?: boolean }) {
  const params = useStore((s) => s.payload?.params);
  const derived = useStore((s) => s.derived);
  const t = useT();
  const [yaw, setYaw] = useState(YAW0);
  const [pitch, setPitch] = useState(PITCH0);
  const [water, setWater] = useState(true);
  /** Whether the preview is unfolded.  Only the sidebar offers this: the page
      holds the picture because that is what it is for, so folding it there
      would leave a header and nothing else.  The count in the header stays
      either way, which is what the strip is worth having folded. */
  const [open, setOpen] = useState(true);
  const drag = useRef<{ x: number; y: number } | null>(null);
  /** The movement the pointer has reported since the last frame, and the frame
      that will apply it -- see `apply`. */
  const moved = useRef({ x: 0, y: 0 });
  const frame = useRef(0);
  const box = useRef<SVGSVGElement | null>(null);
  /** How many CSS pixels one placed unit comes out as -- the number a placed
      size has to be divided by to land on a stated pixel size.  See
      `LABEL_PX`. */
  const [pxPerUnit, setPxPerUnit] = useState(0);

  const mesh = useMemo(
    () => readMesh(params ?? [], derived?.values ?? {}),
    [params, derived],
  );
  /** The corners and the particles, centred on the middle of what is drawn and
      scaled so its longest side is 2 units -- so the picture is the same size
      whatever units the case is written in.  `radius` is how far the furthest
      of them is from that middle, which is what the viewBox has to hold: a
      rotation only ever shortens a projected distance, so that one number fits
      it all at every angle rather than at the one it opens at. */
  const placed = useMemo(
    () => place(mesh.points, mesh.spheres, stage ? mesh.water : null),
    [mesh, stage],
  );
  /** The water box's corners in the placed frame, in the bit-numbered order
      `BOX_EDGES` is written against. */
  const waterCorners = placed.water ? boxCorners(placed.water) : [];
  /** One arrow per face, out of its middle along the normal its own corner
      order gives -- the right-hand rule, and nothing more, so a face whose
      nodes are listed the wrong way round shows an arrow pointing *into* the
      box.  That is the check the corner orders were repaired by, made visible:
      a face of a closed mesh points outwards exactly when its corners are
      wound the way the mesh's own cells wind them. */
  const arrows = useMemo(
    () => mesh.faces.map((f) => faceArrow(f.nodes.map((n) => placed.points[n] as Point))),
    [mesh, placed],
  );
  // The arrows reach out past the box, so the frame has to hold them as well: a
  // glyph running off the edge would be the one face that cannot be judged.
  const reach = Math.max(placed.radius, ...arrows.map((a) => Math.hypot(...a.tip)));
  // How much air the frame leaves around that is the one thing that sets how
  // large the picture comes out.  Both places crop close: the page's column is
  // far wider than the drawing, so margin there is size given away, and the
  // sidebar's card is small enough that the drawing wants every pixel of it --
  // the picture is the point of the card, not the space around it.
  const pad = stage ? 1.05 : 1.02;
  // The top edge holds a little more than the foot does: the corner dots carry
  // labels whose ink reaches above them, and nothing is drawn below its own
  // extreme.  `placed.radius` bounds every corner, so a label over the highest
  // one is bounded by the radius plus its own height.  The drawing therefore
  // sits low in the card rather than dead centre -- which is what keeps the top
  // row of numbers on the picture.
  const room = reach * pad;
  const top = Math.max(room, (placed.radius + LABEL_TOP) * pad);
  // A square frame fits the sidebar's square card.  The page's column is wide
  // and the drawing is not: there the frame is narrowed to what is actually
  // drawn, which hands the *height* the binding role -- so the mesh grows to
  // fill the card instead of the frame reserving width nothing reaches into.
  const halfW = room * (stage ? 1.25 : 1);

  /**
   * The drawing's own scale, measured off the element rather than worked out
   * from the CSS: the `viewBox` fits itself into whatever box it is given, so
   * the only honest source for "how big is a placed unit here" is the box.  The
   * two ratios are `preserveAspectRatio`'s own `meet` rule -- the frame is
   * scaled to fit, which is the smaller of the two -- and re-measured on every
   * resize, because the window's height moves the whole picture's size.
   *
   * Only the page asks: the preview draws its labels in placed units, which is
   * a size that follows the picture, and stays as it was.
   */
  useEffect(() => {
    const el = box.current;
    if (!el || !stage) return;
    const measure = () => {
      const r = el.getBoundingClientRect();
      const scale = Math.min(r.width / (halfW * 2), r.height / (top + room));
      setPxPerUnit(scale > 0 && Number.isFinite(scale) ? scale : 0);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [stage, halfW, top, room]);

  /** What the vertex labels are drawn at here.  Zero until the first
      measurement lands, and zero again if the box has no size at all -- the
      placed size is a decent answer either way, and the wrong one for at most
      one frame. */
  const labelSize = stage && pxPerUnit ? LABEL_PX / pxPerUnit : LABEL_UNITS;

  const cosY = Math.cos(yaw);
  const sinY = Math.sin(yaw);
  const cosP = Math.cos(pitch);
  const sinP = Math.sin(pitch);
  /** Z-up, as the dictionaries are: yaw turns the box about the vertical axis,
      pitch tips its top towards the reader.  `depth` is along the line of
      sight, so the faces can be drawn far-to-near. */
  const project = (p: Point) => {
    const x1 = p[0] * cosY - p[1] * sinY;
    const y1 = p[0] * sinY + p[1] * cosY;
    return { x: x1, y: -(y1 * sinP + p[2] * cosP), depth: y1 * cosP - p[2] * sinP };
  };

  const quads = mesh.faces.map((f, i) => {
    const corners = f.nodes.map((n) => project(placed.points[n] as Point));
    return {
      i,
      patch: f.patch,
      corners,
      depth: corners.reduce((a, q) => a + q.depth, 0) / corners.length,
    };
  });
  /** Every filled shape, far to near.  Faces and particles share one list
      because a sphere inside the box has to be covered by the faces in front
      of it and to cover the ones behind -- the same rule the faces follow
      among themselves.  An orthographic projection turns a sphere into a disc
      of its own radius, so a particle is a circle and nothing more. */
  const shapes = [
    ...quads.map((q) => {
      const hue = HUES[mesh.patches.indexOf(q.patch) % HUES.length];
      return {
        depth: q.depth,
        node: (
          <polygon
            key={`f${q.i}`}
            points={q.corners.map((c) => `${c.x},${c.y}`).join(" ")}
            fill={hue}
            fillOpacity={0.16}
            stroke={hue}
            strokeOpacity={0.85}
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
            strokeLinejoin="round"
          />
        ),
      };
    }),
    ...placed.spheres.map((s, i) => {
      const p = project(s.c);
      return {
        depth: p.depth,
        node: (
          <circle
            key={`p${i}`}
            cx={p.x}
            cy={p.y}
            r={s.r}
            fill="currentColor"
            fillOpacity={0.28}
            stroke="currentColor"
            strokeOpacity={0.95}
            strokeWidth={1.2}
            vectorEffect="non-scaling-stroke"
          />
        ),
      };
    }),
  ].sort((a, b) => a.depth - b.depth);

  const dots = placed.points.flatMap((p, i) => (p ? [{ i, ...project(p) }] : []));
  const nPoints = dots.length;

  const reset = () => {
    setYaw(YAW0);
    setPitch(PITCH0);
  };

  /** Apply whatever the pointer has reported since the last frame.

      Move events arrive far faster than the screen repaints: a 1000 Hz mouse
      is a thousand state updates a second, and every one of them is a render
      of the whole picture.  Feeding them to React one at a time is what made
      the box trail the cursor -- the queue grew faster than the frames could
      drain it, so the view fell further behind the longer the drag went on.
      Collecting the deltas and applying them once per frame caps the work at
      the rate anything can be seen to move, whatever the mouse reports. */
  const apply = () => {
    frame.current = 0;
    const d = moved.current;
    moved.current = { x: 0, y: 0 };
    if (!d.x && !d.y) return;
    setYaw((a) => a + d.x * 0.012);
    // Tipped past vertical the box reads as seen from underneath, which is a
    // place to get stuck rather than a view to look from.
    setPitch((a) => clamp(a + d.y * 0.012));
  };

  /** The drag is over.  Whatever arrived since the last frame still lands, so
      the box ends where the cursor is rather than a frame behind it. */
  const stop = (e: ReactPointerEvent<SVGSVGElement>) => {
    drag.current = null;
    if (frame.current) {
      cancelAnimationFrame(frame.current);
      apply();
    }
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
  };

  return (
    // `notranslate` (a Google Translate convention, not a Tailwind class) keeps
    // the browser's translation machinery out of the box: a drag across the
    // labels otherwise reads as a text selection and brings up the translate
    // bubble over a picture that has nothing to translate.
    //
    // A card in its own right, level with the derived panel rather than a
    // section inside it: what it shows is the *case*, not one of the metrics.
    // The header strip runs to the card's edges the way the parameter cards'
    // do, which is what the negative margins over the root's padding are for.
    <div className="glass lift notranslate shrink-0 overflow-hidden rounded-lg px-3 py-2">
      <div className="-mx-3 -mt-2 flex items-center gap-1.5 border-b border-line-soft bg-wash px-3 py-1.5">
        <h3 className="text-[10.5px] font-medium uppercase tracking-wider text-ink-3">
          {/* Named for what it is in each place: the sidebar's strip is a
              preview and says so, while the page is the mesh itself -- the tab
              next to it is already called Geometry inspection, so calling the
              card that too would name the page twice over. */}
          {t.t(stage ? "Mesh geometry" : "Geometry preview")}
        </h3>
        <span className="ml-auto font-mono text-[10px] text-ink-4">
          {t.t("{n} vertices · {m} faces", { n: nPoints, m: quads.length })}
        </span>
        <button
          onClick={reset}
          title={t.t("Reset the view")}
          aria-label={t.t("Reset the view")}
          className="rounded p-0.5 text-ink-4 transition hover:text-ink"
        >
          <IconUndo width={12} height={12} />
        </button>
        {!stage && (
          // The fold control is the one thing on this strip meant to be
          // *found*, so unlike the reset glyph beside it, it wears the accent:
          // a folded preview is a card with no picture, and a hairline chevron
          // in the corner is not an answer to "where did it go".  Filled and
          // bordered like the sidebar's own collapse handle.
          <button
            onClick={() => setOpen((v) => !v)}
            title={t.t(open ? "Fold the preview" : "Unfold the preview")}
            aria-label={t.t(open ? "Fold the preview" : "Unfold the preview")}
            aria-expanded={open}
            className="grid h-[18px] w-[18px] place-items-center rounded border border-accent/50 bg-accent/20 text-accent transition hover:bg-accent/35 hover:text-accent-ink active:scale-95"
          >
            {/* Points up while open -- the way it folds -- and down while
                folded, which is the way it comes back. */}
            <IconChevron
              width={13}
              height={13}
              strokeWidth={2.2}
              className={`transition ${open ? "rotate-180" : ""}`}
            />
          </button>
        )}
      </div>

      {/* Folded, the card is its header and the count on it -- which is the
          whole of what the picture says in one line. */}
      {!open ? null : nPoints === 0 ? (
        <p className="mt-1.5 text-[10px] leading-relaxed text-ink-4">
          {t.t("No vertices or faces were read from the mesh card.")}
        </p>
      ) : (
        <>
          <div
            className={`relative mt-1.5 ${
              stage
                ? // The page's height is what is left under the two bars, the
                  // hint and the card's own header -- so the whole picture,
                  // legend included, is on screen without scrolling.  The
                  // subtrahend is those fixed parts plus a little slack, so the
                  // card's foot lands just above the status bar rather than
                  // short of it.  The floor keeps it a picture in a short
                  // window, where the alternative is a strip too thin to read,
                  // and the ceiling stops it outgrowing the column on a very
                  // tall one.
                  "h-[calc(100vh-18rem)] min-h-[16rem] max-h-[40rem]"
                  : "h-[21rem]"
            }`}
          >
            <svg
              ref={box}
              viewBox={`${-halfW} ${-top} ${halfW * 2} ${top + room}`}
              className="h-full w-full cursor-grab touch-none select-none text-ink-2 active:cursor-grabbing"
              onPointerDown={(e) => {
                // The left button only: a right-click opens the browser menu
                // over the box, and grabbing the mesh through it just leaves
                // the view turned when the menu is dismissed.
                if (e.button !== 0) return;
                drag.current = { x: e.clientX, y: e.clientY };
                moved.current = { x: 0, y: 0 };
                e.currentTarget.setPointerCapture(e.pointerId);
              }}
              onPointerMove={(e) => {
                const from = drag.current;
                if (!from) return;
                // A drag the browser cancelled -- the window lost the pointer,
                // a menu opened over it -- can leave the capture behind, and
                // with no button down there is nothing to follow.
                if (!e.buttons) {
                  drag.current = null;
                  return;
                }
                moved.current.x += e.clientX - from.x;
                moved.current.y += e.clientY - from.y;
                from.x = e.clientX;
                from.y = e.clientY;
                if (!frame.current) frame.current = requestAnimationFrame(apply);
              }}
              onPointerUp={stop}
              onPointerCancel={stop}
              onDoubleClick={reset}
            >
              <title>{t.t("Drag to rotate")}</title>
              {shapes.map((s) => s.node)}
              {/* Over the faces rather than sorted among them: it is a region
                  of the case, not a surface of the mesh, and a dashed wireframe
                  half-hidden behind a translucent quad would only be a puzzle.
                  Hidden, it still frames the picture -- the view does not jump
                  when it is switched on. */}
              {water &&
                waterCorners.length > 0 &&
                BOX_EDGES.map(([a, b], i) => {
                  const p = project(waterCorners[a]);
                  const q = project(waterCorners[b]);
                  return (
                    <line
                      key={`w${i}`}
                      x1={p.x}
                      y1={p.y}
                      x2={q.x}
                      y2={q.y}
                      stroke={WATER_HUE}
                      strokeWidth={1.4}
                      strokeOpacity={0.9}
                      strokeDasharray="6 4"
                      strokeLinecap="round"
                      vectorEffect="non-scaling-stroke"
                    />
                  );
                })}
              {/* Above the faces rather than sorted among them: a translucent
                  quad would not hide an arrow, only dim it, and the whole point
                  of the glyph is the direction it points in. */}
              {arrows.map((a, i) => {
                const from = project(a.at);
                const to = project(a.tip);
                const dx = to.x - from.x;
                const dy = to.y - from.y;
                const len = Math.hypot(dx, dy);
                // A normal pointing straight at the reader projects to nothing.
                // The round cap turns the zero-length shaft into a dot, and the
                // head has no direction to point in, so it is left off.
                const head =
                  len < 0.02
                    ? ""
                    : (() => {
                        const ux = dx / len;
                        const uy = dy / len;
                        const bx = -uy * HEAD_W;
                        const by = ux * HEAD_W;
                        const cx = to.x - ux * HEAD_L;
                        const cy = to.y - uy * HEAD_L;
                        return `${cx + bx},${cy + by} ${to.x},${to.y} ${cx - bx},${cy - by}`;
                      })();
                return (
                  <g key={`n${i}`} className="text-ink-3">
                    <line
                      x1={from.x}
                      y1={from.y}
                      x2={to.x}
                      y2={to.y}
                      stroke="currentColor"
                      strokeWidth={1.2}
                      strokeLinecap="round"
                      vectorEffect="non-scaling-stroke"
                    />
                    {head && (
                      <polyline
                        points={head}
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={1.2}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        vectorEffect="non-scaling-stroke"
                      />
                    )}
                  </g>
                );
              })}
              {dots.map((d) => (
                <g key={d.i}>
                  <circle cx={d.x} cy={d.y} r={0.0275} fill="currentColor" />
                  {/* The index the face table writes in `vnodes`, prefixed `n`
                      for node -- these are the numbers a face row refers to,
                      so they are worth reading off the picture.  In the placed
                      units rather than the case's own, which are never reached:
                      the mesh is always scaled to the same size first.  `labelSize`
                      keeps that size in the preview and answers with the legend's
                      on the page -- see `LABEL_PX`. */}
                  <text
                    x={d.x}
                    y={d.y}
                    dx={labelSize * LABEL_DX}
                    dy={labelSize * LABEL_DY}
                    fontSize={labelSize}
                    fill="currentColor"
                    opacity={0.7}
                    className="font-mono"
                  >
                    {`n${d.i}`}
                  </text>
                </g>
              ))}
            </svg>

            {/* The corner glyph: drawn with the very same projection, so it
                turns with the box and answers "which way is x" without hunting
                for a face.  A viewBox of its own, since it is a fixed fraction
                of the panel rather than of the mesh -- an eighth of the width
                in the sidebar, half that on the page, where the glyph would
                otherwise grow with the box -- and not draggable, so a drag that
                starts on it still turns the box. */}
            <svg
              viewBox="-1.25 -1.25 2.5 2.5"
              className={`pointer-events-none absolute left-1 top-1 aspect-square ${
                stage ? "w-[6.25%]" : "w-[12.5%]"
              }`}
            >
              {AXES.map((a) => {
                const tip = project(a.dir);
                return (
                  <g key={a.name}>
                    <line
                      x1={0}
                      y1={0}
                      x2={tip.x * 0.72}
                      y2={tip.y * 0.72}
                      stroke={a.hue}
                      strokeWidth={1.4}
                      strokeLinecap="round"
                      vectorEffect="non-scaling-stroke"
                    />
                    <text
                      x={tip.x * 0.98}
                      y={tip.y * 0.98}
                      fontSize={0.55}
                      fill={a.hue}
                      textAnchor="middle"
                      dominantBaseline="central"
                      className="font-mono"
                    >
                      {a.name}
                    </text>
                  </g>
                );
              })}
              <circle r={0.08} fill="currentColor" />
            </svg>
          </div>

          {/* The card's foot: what the colours mean on the left, and the one
              thing about the picture that can be switched -- the water box --
              on the right, where it is the last thing on the page. */}
          {(mesh.patches.length > 1 || (stage && waterCorners.length > 0)) && (
            <div
              className={`mt-1 flex flex-wrap items-center gap-y-0.5 ${
                stage ? "gap-x-[13px]" : "gap-x-2.5"
              }`}
            >
              {mesh.patches.map((name, i) => (
                <span
                  key={name}
                  className={`flex items-center gap-1 text-ink-4 ${
                    stage ? "text-[17px]" : "text-[15px]"
                  }`}
                >
                  <span
                    className="h-2 w-2 shrink-0 rounded-[2px]"
                    style={{ background: HUES[i % HUES.length] }}
                  />
                  {name}
                </span>
              ))}

              {stage && waterCorners.length > 0 && (
                <div className="ml-auto flex items-center gap-1.5">
                  {/* The same size as the patch names it stands beside: it is
                      one more entry in the legend, not a caption. */}
                  <span
                    className={`flex items-center gap-1 text-ink-4 ${
                      stage ? "text-[17px]" : "text-[15px]"
                    }`}
                  >
                    <span
                      className="w-3 shrink-0 border-t border-dashed"
                      style={{ borderColor: WATER_HUE }}
                    />
                    {t.t("Initial water")}
                  </span>
                  <div className="flex gap-0.5 rounded border border-line p-0.5">
                    {[false, true].map((on) => (
                      <button
                        key={String(on)}
                        onClick={() => setWater(on)}
                        className={`rounded px-1.5 py-0.5 text-[10px] transition ${
                          water === on ? "bg-accent/20 text-accent" : "text-ink-3 hover:text-ink"
                        }`}
                      >
                        {t.t(on ? "Show" : "Hide")}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/** The pitch stays inside a right angle either way, so the box tips but never
    turns over. */
function clamp(v: number): number {
  const limit = Math.PI / 2 - 0.05;
  return Math.max(-limit, Math.min(limit, v));
}

/** The mesh the two `blockMeshDict` tables describe and the particles the DEM
    block creates, from the effective values (the file's, overlaid with pending
    edits).  A table the reader could not place simply contributes nothing. */
function readMesh(params: Param[], values: Record<string, ParamValue>): Mesh {
  const byId = new Map(params.map((p) => [p.id, p]));
  const vParam = byId.get("mesh.vertices");
  const fParam = byId.get("mesh.faces");
  const pParam = byId.get("dem.particles");

  const points: (Point | null)[] = [];
  for (const row of rowsOf(vParam, values)) {
    points.push(Array.isArray(row) ? triple(row) : null);
  }

  // Which box holds which cell, and which cell of a particle row holds which
  // number, is the rule's business -- so it is read off the declaration rather
  // than assumed: the file order is the column order.
  const at = (p: Param | undefined, name: string, fallback: number) => {
    const j = (p?.columns ?? []).findIndex((c) => c.name === name);
    return j < 0 ? fallback : j;
  };

  const patchCol = at(fParam, "vpatch", 0);
  const nodesCol = at(fParam, "vnodes", 1);

  const faces: Mesh["faces"] = [];
  const patches: string[] = [];
  for (const row of rowsOf(fParam, values)) {
    if (!Array.isArray(row)) continue;
    const patch = String(row[patchCol] ?? "");
    const indices = String(row[nodesCol] ?? "")
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .map(Number);
    if (indices.length < 3) continue;
    // A face is only drawable whole: one corner the rules could not resolve
    // drops the face rather than bending it through the origin.
    if (indices.some((i) => !points[i])) continue;
    faces.push({ patch, nodes: indices });
    if (!patches.includes(patch)) patches.push(patch);
  }

  const px = at(pParam, "valx", 1);
  const py = at(pParam, "valy", 2);
  const pz = at(pParam, "valz", 3);
  const pd = at(pParam, "vald", 4);

  const spheres: Sphere[] = [];
  for (const row of rowsOf(pParam, values)) {
    if (!Array.isArray(row)) continue;
    const c = triple([row[px], row[py], row[pz]]);
    const d = Number(row[pd]);
    // A particle whose row does not resolve is skipped rather than drawn at
    // the origin, and a diameter that is not positive is not a sphere.
    if (!c || !(d > 0)) continue;
    spheres.push({ c, r: d / 2 });
  }

  // The water box, from the six `setFieldsDict` bounds: the only part of the
  // picture that comes from a card other than the mesh's, which is why it is
  // drawn in a style of its own.
  const num = (id: string): number | null => {
    const p = byId.get(id);
    if (!p) return null;
    const v = p.id in values ? values[p.id] : p.value;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };
  const lo: number[] = [];
  const hi: number[] = [];
  for (const axis of ["x", "y", "z"]) {
    const a = num(`mesh.sf.${axis}min`);
    const b = num(`mesh.sf.${axis}max`);
    // A bound the rules could not read, or a side that is not a volume, is not
    // a box: half a box drawn round the mesh would be worse than none.
    if (a === null || b === null || b <= a) break;
    lo.push(a);
    hi.push(b);
  }
  const water: Box | null =
    lo.length === 3
      ? { lo: [lo[0], lo[1], lo[2]], hi: [hi[0], hi[1], hi[2]] }
      : null;

  return { points, faces, patches, spheres, water };
}

/** The eight corners of a box in the bit-numbered order `BOX_EDGES` joins. */
function boxCorners({ lo, hi }: Box): Point[] {
  return [0, 1, 2, 3, 4, 5, 6, 7].map((c) => [
    c & 4 ? hi[0] : lo[0],
    c & 2 ? hi[1] : lo[1],
    c & 1 ? hi[2] : lo[2],
  ]);
}

/** A table's rows, pending edits first (see `Derived.values`). */
function rowsOf(p: Param | undefined, values: Record<string, ParamValue>): unknown[] {
  if (!p) return [];
  const v = p.id in values ? values[p.id] : p.value;
  return Array.isArray(v) ? v : [];
}

function triple(row: unknown[]): Point | null {
  const n = [Number(row[0]), Number(row[1]), Number(row[2])];
  return n.every(Number.isFinite) ? [n[0], n[1], n[2]] : null;
}

/** A face's middle and where its normal reaches from there.

    Newell's method rather than one cross product of the first three corners:
    the corners of a face the writer made slightly non-planar still average out
    a normal, where a single cross product would tilt with whichever corner
    came first -- and a face is drawn straight from whatever the file says. */
function faceArrow(corners: Point[]): { at: Point; tip: Point } {
  const at: Point = [0, 0, 0];
  const n: Point = [0, 0, 0];
  for (let i = 0; i < corners.length; i++) {
    const a = corners[i];
    const b = corners[(i + 1) % corners.length];
    at[0] += a[0] / corners.length;
    at[1] += a[1] / corners.length;
    at[2] += a[2] / corners.length;
    n[0] += (a[1] - b[1]) * (a[2] + b[2]);
    n[1] += (a[2] - b[2]) * (a[0] + b[0]);
    n[2] += (a[0] - b[0]) * (a[1] + b[1]);
  }
  const m = Math.hypot(...n) || 1;
  return {
    at,
    tip: [
      at[0] + (n[0] / m) * ARROW,
      at[1] + (n[1] / m) * ARROW,
      at[2] + (n[2] / m) * ARROW,
    ],
  };
}

/** Centre everything that is drawn on the middle of it, scale the longest side
    to 2, and report how far the furthest part of it then sits from that middle.

    The particles and the water box are framed along with the corners: one the
    table puts outside the mesh, or a box that starts above the domain lid, is
    exactly what the picture has to show, and a frame drawn around the mesh
    alone would cut it off. */
function place(
  points: (Point | null)[],
  spheres: Sphere[],
  water: Box | null,
): {
  points: (Point | null)[];
  spheres: Sphere[];
  water: Box | null;
  radius: number;
} {
  const good = points.filter((p): p is Point => !!p);
  // A sphere lies exactly inside the box of centre plus or minus the radius,
  // axis by axis, so these six points bound it -- nothing is left outside.
  const bounds = spheres.flatMap((s) =>
    [0, 1, 2].flatMap((a) => {
      const lo = s.c.slice() as Point;
      const hi = s.c.slice() as Point;
      lo[a] -= s.r;
      hi[a] += s.r;
      return [lo, hi];
    }),
  );
  const all = [...good, ...bounds, ...(water ? boxCorners(water) : [])];
  if (!all.length) return { points, spheres, water, radius: 1 };
  const axes = [0, 1, 2];
  const lo = axes.map((a) => Math.min(...all.map((p) => p[a])));
  const hi = axes.map((a) => Math.max(...all.map((p) => p[a])));
  const mid = axes.map((a) => (lo[a] + hi[a]) / 2);
  const span = Math.max(...axes.map((a) => hi[a] - lo[a])) || 1;
  const k = 2 / span;
  // The scaling is the same on every axis and has no rotation, so a box stays
  // a box: its two corners are all that has to be carried over.
  const fit = (p: Point): Point => [
    (p[0] - mid[0]) * k,
    (p[1] - mid[1]) * k,
    (p[2] - mid[2]) * k,
  ];
  const moved = points.map((p) => (p ? fit(p) : null));
  const balls = spheres.map((s) => ({ c: fit(s.c), r: s.r * k }));
  const box = water ? { lo: fit(water.lo), hi: fit(water.hi) } : null;
  const radius = Math.max(
    ...moved.filter((p): p is Point => !!p).map((p) => Math.hypot(...p)),
    ...balls.map((s) => Math.hypot(...s.c) + s.r),
    ...(box ? boxCorners(box).map((p) => Math.hypot(...p)) : []),
  );
  return { points: moved, spheres: balls, water: box, radius: radius || 1 };
}
