import { useEffect } from "react";
import { useT } from "../hooks";
import { IconAlert } from "./Icons";

interface Props {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Used for actions that overwrite files without producing a diff first. */
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  danger,
  onConfirm,
  onCancel,
}: Props) {
  const t = useT();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
      if (e.key === "Enter") onConfirm();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onCancel, onConfirm]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-base/75 backdrop-blur-sm" onClick={onCancel} />
      <div className="anim-in glass-strong relative w-full max-w-md rounded-xl p-4">
        <div className="flex items-start gap-3">
          <div
            className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg ${
              danger ? "bg-warn/15 text-warn" : "bg-accent/15 text-accent"
            }`}
          >
            <IconAlert width={16} height={16} />
          </div>
          <div className="min-w-0">
            <h2 className="text-[13px] font-medium">{title}</h2>
            <p className="mt-1 whitespace-pre-wrap text-[11.5px] leading-relaxed text-ink-3">
              {body}
            </p>
          </div>
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="btn-glass rounded-md px-3 py-1.5 text-[12px] text-ink-2 transition"
          >
            {t.t("Cancel")}
          </button>
          <button
            onClick={onConfirm}
            className={`btn-gloss rounded-md px-3.5 py-1.5 text-[12px] font-medium ${
              danger ? "btn-gloss-warn bg-warn text-accent-ink" : "bg-accent text-accent-ink"
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
