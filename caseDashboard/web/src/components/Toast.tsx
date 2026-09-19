import { useStore } from "../store";
import { useT } from "../hooks";
import { IconAlert, IconCheck, IconCross, IconInfo } from "./Icons";
import type { ToastKind } from "../store";

const STYLE: Record<ToastKind, { ring: string; text: string; icon: typeof IconCheck }> = {
  ok: { ring: "ring-ok/40", text: "text-ok", icon: IconCheck },
  warn: { ring: "ring-warn/40", text: "text-warn", icon: IconAlert },
  error: { ring: "ring-error/40", text: "text-error", icon: IconAlert },
  info: { ring: "ring-info/40", text: "text-info", icon: IconInfo },
};

export function Toasts() {
  const toasts = useStore((s) => s.toasts);
  const dismiss = useStore((s) => s.dismissToast);
  const t = useT();
  if (!toasts.length) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(28rem,calc(100vw-2rem))] flex-col gap-2">
      {toasts.map((toast) => {
        const s = STYLE[toast.kind];
        const Icon = s.icon;
        return (
          <div
            key={toast.id}
            className={`anim-in glass-strong lift pointer-events-auto flex gap-3 rounded-lg p-3 ring-1 ${s.ring}`}
          >
            <Icon className={`mt-0.5 shrink-0 ${s.text}`} />
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-medium text-ink">{toast.text}</div>
              {toast.detail && (
                <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] leading-relaxed text-ink-3">
                  {toast.detail}
                </pre>
              )}
            </div>
            <button
              onClick={() => dismiss(toast.id)}
              className="shrink-0 self-start rounded p-0.5 text-ink-3 transition hover:bg-panel-3 hover:text-ink"
              aria-label={t.t("Dismiss")}
            >
              <IconCross width={13} height={13} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
