import clsx from "clsx";
import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Button } from "./Button";

const FOCUSABLE = 'a[href],button:not([disabled]),textarea,input,select,[tabindex]:not([tabindex="-1"])';

/** Shared modal behaviour: Esc to close, focus trap, body scroll lock, focus restore. */
function useDialog(open: boolean, onClose: () => void) {
  const panelRef = useRef<HTMLDivElement>(null);
  // Latest onClose without re-running the effect (which would steal focus on every render).
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseRef.current();
      if (event.key !== "Tab" || !panelRef.current) return;
      const items = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) return;
      const first = items[0]!;
      const last = items[items.length - 1]!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, [open]);
  return panelRef;
}

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}

export function Drawer({ open, onClose, title, children, footer }: DrawerProps) {
  const panelRef = useDialog(open, onClose);
  const titleId = useId();
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 animate-fade-in bg-black/60 backdrop-blur-sm" onClick={onClose} aria-hidden />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="relative flex h-full w-full max-w-[720px] animate-slide-in flex-col border-l border-border bg-surface shadow-2xl"
      >
        <header className="flex items-start justify-between gap-4 border-b border-border p-5">
          <div id={titleId} className="min-w-0 flex-1">
            {title}
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close" icon={<X className="h-4 w-4" />} />
        </header>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
        {footer && <footer className="border-t border-border p-5">{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
}

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  actions: ReactNode;
}

export function Modal({ open, onClose, title, children, actions }: ModalProps) {
  const panelRef = useDialog(open, onClose);
  const titleId = useId();
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 animate-fade-in bg-black/60 backdrop-blur-sm" onClick={onClose} aria-hidden />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={clsx("glass relative w-full max-w-md animate-fade-in bg-surface p-6 shadow-2xl")}
      >
        <h2 id={titleId} className="text-lg font-semibold">
          {title}
        </h2>
        <div className="mt-2 text-sm text-muted">{children}</div>
        <div className="mt-6 flex justify-end gap-2">{actions}</div>
      </div>
    </div>,
    document.body,
  );
}
