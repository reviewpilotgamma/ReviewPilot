import { CheckCircle2, Info, XCircle } from "lucide-react";
import { createContext, useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import clsx from "clsx";

type ToastKind = "success" | "error" | "info";
interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

export interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

export const ToastContext = createContext<ToastApi | null>(null);

const DISMISS_MS = 4000;
const ICONS = { success: CheckCircle2, error: XCircle, info: Info } as const;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const push = useCallback((kind: ToastKind, message: string) => {
    const id = nextId.current++;
    setToasts((current) => [...current.slice(-3), { id, kind, message }]);
    window.setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), DISMISS_MS);
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      success: (m) => push("success", m),
      error: (m) => push("error", m),
      info: (m) => push("info", m),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2" aria-live="polite">
        {toasts.map((toast) => {
          const Icon = ICONS[toast.kind];
          return (
            <div
              key={toast.id}
              role="status"
              className={clsx(
                "glass pointer-events-auto flex animate-fade-in items-start gap-2 px-4 py-3 text-sm shadow-lg",
                toast.kind === "success" && "border-emerald/40",
                toast.kind === "error" && "border-rose/40",
              )}
            >
              <Icon
                className={clsx(
                  "mt-0.5 h-4 w-4 shrink-0",
                  toast.kind === "success" && "text-emerald",
                  toast.kind === "error" && "text-rose",
                  toast.kind === "info" && "text-violet",
                )}
              />
              <span>{toast.message}</span>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
