import { useEffect, useMemo, useRef } from "react";
import { useStore } from "../store";
import { useT } from "../hooks";
import { shortenFile } from "../format";
import { IconCheck, IconFile, IconSpinner } from "./Icons";

/**
 * The file itself, in the panel, for parameters the rules cannot place.
 *
 * There is no rule saying where such a line goes, so there is nothing the
 * dashboard could usefully splice -- the honest thing is to show the whole file
 * and take back whatever the user makes of it.  It looks like the write preview
 * because it is the same kind of thing: the file, as text, before it is saved.
 */
export function FileEditor() {
  const editor = useStore((s) => s.editor);
  const busy = useStore((s) => s.busy);
  const close = useStore((s) => s.closeEditor);
  const save = useStore((s) => s.saveFile);
  const setText = useStore((s) => s.setEditorText);
  const gutter = useRef<HTMLPreElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const t = useT();

  useEffect(() => {
    if (!editor) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [editor, busy, close]);

  const text = editor?.text ?? "";
  const lineNumbers = useMemo(
    () => Array.from({ length: text.split("\n").length }, (_, i) => i + 1).join("\n"),
    [text],
  );

  if (!editor) return null;

  const dirty = editor.text !== editor.saved;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-base/75 backdrop-blur-sm"
        onClick={() => !busy && close()}
      />

      <div className="anim-in glass-strong relative flex max-h-[88vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl">
        <header className="flex shrink-0 items-center gap-3 border-b border-line px-4 py-3">
          <IconFile width={16} height={16} className="text-accent" />
          <div className="min-w-0">
            <h2 className="truncate font-mono text-[13px]">{shortenFile(editor.file)}</h2>
            <p className="text-[11px] text-ink-3">
              {editor.eol === "crlf" ? "CRLF" : "LF"} {t.t("line endings")} ·{" "}
              {t.t("{n} lines", { n: lineCount(editor.text) })} ·{" "}
              {dirty ? (
                <span className="text-dirty">{t.t("Unsaved")}</span>
              ) : (
                t.t("Unchanged")
              )}
            </p>
          </div>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <button
              onClick={close}
              disabled={busy}
              className="btn-glass rounded-md px-3 py-1.5 text-[12px] text-ink-2 transition disabled:opacity-40"
            >
              {t.t("Cancel")}
            </button>
            <button
              onClick={() => void save()}
              disabled={busy || !dirty}
              className="btn-gloss flex items-center gap-1.5 rounded-md bg-accent px-3.5 py-1.5 text-[12px] font-medium text-accent-ink disabled:opacity-40"
            >
              {busy ? <IconSpinner width={13} height={13} /> : <IconCheck width={13} height={13} />}
              {t.t("Save")}
            </button>
          </div>
        </header>

        {/* The gutter is a plain list of numbers kept in step by scrollTop; both
            sides share the font and line-height, and the textarea does not wrap,
            so a line's number stays next to its line. */}
        <div className="flex h-[58vh] min-h-0 bg-field font-mono text-[11px] leading-[1.6]">
          <pre
            ref={gutter}
            aria-hidden
            className="m-0 w-11 shrink-0 select-none overflow-hidden border-r border-line-soft py-2 pr-1.5 text-right font-mono text-ink-4"
          >
            {lineNumbers}
          </pre>
          <textarea
            ref={area}
            value={editor.text}
            onChange={(e) => setText(e.target.value)}
            onScroll={() => {
              if (gutter.current && area.current) {
                gutter.current.scrollTop = area.current.scrollTop;
              }
            }}
            spellCheck={false}
            wrap="off"
            className="min-w-0 flex-1 resize-none whitespace-pre bg-transparent px-2 py-2 font-mono text-[11px] leading-[1.6] text-ink-2 outline-none"
          />
        </div>

        <p className="shrink-0 border-t border-line px-4 py-2 text-[10.5px] text-ink-4">
          {t.t(
            "Nothing is written until you press Save; a snapshot is taken first, and Roll back in the top bar undoes it.",
          )}
        </p>
      </div>
    </div>
  );
}

const lineCount = (text: string) => text.split("\n").length;
