import { useMemo, useState } from "react";
import { useStore } from "../store";
import { useIssueMap, useParamsByGroup, useT } from "../hooks";
import { LEVEL_RANK, shortenFile } from "../format";
import { ParamField } from "./ParamField";
import { IconFile } from "./Icons";

interface Props {
  groupId: string;
}

/**
 * Params are laid out per source file rather than one flat list: the whole
 * point of the dashboard is that a single quantity is duplicated across files,
 * so keeping file boundaries visible makes the duplication legible.  A param
 * may opt out of its file's card (see `Param.card`) when it is a separate
 * concern that merely happens to live in the same dictionary -- and a card may
 * cover several files, which is why the header names all of them.
 */
export function ParamPanel({ groupId }: Props) {
  const params = useParamsByGroup(groupId);
  const payload = useStore((s) => s.payload);
  const focusParam = useStore((s) => s.focusParam);
  const inactive = useStore((s) => s.derived?.inactive_params);
  const openFile = useStore((s) => s.openFile);
  const issues = useIssueMap();
  const t = useT();

  /**
   * The route a case did not take is noise on first read -- `two_phase_sphere_settling`
   * would otherwise open on 26 grey rows that cannot be edited -- so it starts
   * folded.  One flag for the whole panel, not one per card: the cards are
   * rendered inside a `byCard.map()`, where a hook would break the rules of
   * hooks, and only the DEM card ever has anything to fold.
   */
  const [showUnused, setShowUnused] = useState(false);

  const byCard = useMemo(() => {
    type Card = { key: string; card: string | null; items: typeof params };
    const out: Card[] = [];
    for (const p of params) {
      const key = p.card ?? p.source.file;
      const last = out[out.length - 1];
      if (last && last.key === key) last.items.push(p);
      else out.push({ key, card: p.card, items: [p] });
    }
    return out;
  }, [params]);

  const inactiveSet = useMemo(() => new Set(inactive ?? []), [inactive]);

  /** `Mesh and domain` for the card header; absent entries fall back to the path. */
  const labels = payload?.file_labels ?? {};

  if (!params.length) {
    return (
      <div className="p-8 text-center text-[12px] text-ink-4">
        {t.t("This group has no editable parameters.")}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {byCard.map(({ key, card, items }) => {
        // A card is usually one file, but one that opts out of the per-file
        // layout may gather several -- so the files are read off the items
        // rather than assumed, and every one of them is named in the header.
        const files = [...new Set(items.map((p) => p.source.file))];
        // A card title is a name the backend chose, so it is keyed by the title
        // itself; a file's card falls back to the file's own label.
        const title = card
          ? t.byId("card", card, card)
          : t.byId("file", files[0], labels[files[0]] ?? "");
        // A file that still holds params the rules could not place is the one
        // case where the fix is a line only the user can write, so this is where
        // the file gets opened for editing in the panel.  Counted per file: a
        // card covering three dictionaries has to offer whichever of them is
        // short, not just the one it happens to start with.
        const missing = new Map<string, number>();
        for (const p of items) {
          if (p.status === "unresolved") {
            missing.set(p.source.file, (missing.get(p.source.file) ?? 0) + 1);
          }
        }
        // The other particle-creation route: shown only when asked for.  The
        // count in the header is the number of fields actually on screen.
        const unused = items.filter((p) => p.status === "unused").length;
        const shown =
          showUnused || unused === 0
            ? items
            : items.filter((p) => p.status !== "unused");
        // The rest of a grouped quantity (a domain extent's min/max, a
        // decomposition's x/y/z) is folded into its owner's row, so it never
        // gets a line of its own.  The claim table is built first, which is why
        // a partner sitting *before* its owner still renders once, where the
        // owner is.  Claiming needs the partner to be in `shown`: one folded
        // away by the Show/Hide button degrades to a plain row rather than
        // vanishing with it.
        const byId = new Map(shown.map((p) => [p.id, p]));
        const claimed = new Set(
          shown.flatMap((p) =>
            p.partners.filter((id) => byId.has(id)).map((id) => id),
          ),
        );
        const rows = shown
          .filter((p) => !claimed.has(p.id))
          .map((p) => ({
            a: p,
            rest: p.partners.filter((id) => byId.has(id)).map((id) => byId.get(id)!),
          }));
        return (
          <section
            key={key}
            className="glass lift overflow-hidden rounded-lg"
          >
            <header className="flex items-center gap-2 border-b border-line-soft bg-wash px-3 py-1.5">
              <IconFile width={13} height={13} className="shrink-0 text-ink-3" />
              <span
                className="min-w-0 truncate text-[11.5px] text-ink"
                title={files.join(" · ")}
              >
                {title ? `${title}(` : ""}
                <span className="font-mono text-ink-3">{files.join(" · ")}</span>
                {title ? ")" : ""}
              </span>
              {[...missing].map(([file, n]) => (
                <button
                  key={file}
                  onClick={() => void openFile(file)}
                  className="shrink-0 rounded border border-warn/40 px-1.5 py-0.5 text-[10.5px] text-warn transition hover:bg-warn/10"
                  title={t.t("Open {file} in the panel and add the {n} missing entries by hand", {
                    file,
                    n,
                  })}
                >
                  {files.length > 1
                    ? t.t("Open {file} to add", { file: shortenFile(file) })
                    : t.t("Open file to add")}
                </button>
              ))}
              {unused > 0 && (
                <button
                  onClick={() => setShowUnused((v) => !v)}
                  className="shrink-0 rounded border border-line px-1.5 py-0.5 text-[10.5px] text-ink-3 transition hover:bg-panel-2"
                  title={t.t("This case creates its particles another way; these settings do not apply")}
                >
                  {t.t("Unused {n} · {action}", {
                    n: unused,
                    action: t.t(showUnused ? "Hide" : "Show"),
                  })}
                </button>
              )}
              <span className="ml-auto shrink-0 text-[10.5px] text-ink-4">
                {t.t("{n} items", { n: shown.length })}
              </span>
            </header>

            <div className="grid grid-cols-1 gap-x-3 gap-y-0.5 p-1 lg:grid-cols-2 xl:grid-cols-3">
              {rows.map(({ a, rest }) => (
                <ParamField
                  key={a.id}
                  param={a}
                  partners={rest}
                  focused={[a, ...rest].some((p) => focusParam === p.id)}
                  inactive={[a, ...rest].some((p) => inactiveSet.has(p.id))}
                  issueLevel={mergeLevel([a, ...rest].map((p) => issues[p.id]))}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

/**
 * The heaviest of the consistency levels of a row's params, which share one
 * badge slot.  `LEVEL_RANK` is the panel's one ranking (worst first), and
 * `null` means none of them is named by a problem.
 */
function mergeLevel(
  levels: ("warn" | "error" | undefined)[],
): "warn" | "error" | null {
  let worst: "warn" | "error" | null = null;
  for (const level of levels) {
    if (!level) continue;
    if (worst === null || LEVEL_RANK[level] < LEVEL_RANK[worst]) worst = level;
  }
  return worst;
}
