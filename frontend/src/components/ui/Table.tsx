import clsx from "clsx";
import type { ReactNode } from "react";

export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="text-xs uppercase tracking-wide text-muted">
          <tr>
            {head.map((cell, i) => (
              <th key={i} scope="col" className="px-4 py-3 font-medium">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

interface RowProps {
  children: ReactNode;
  onClick?: () => void;
  label?: string;
}

/** Clickable rows are keyboard accessible (Enter/Space). */
export function Row({ children, onClick, label }: RowProps) {
  return (
    <tr
      className={clsx(
        "border-t border-border transition duration-150",
        onClick && "cursor-pointer hover:bg-violet-soft/40 focus-visible:bg-violet-soft/40",
      )}
      onClick={onClick}
      onKeyDown={(event) => {
        if (onClick && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          onClick();
        }
      }}
      tabIndex={onClick ? 0 : undefined}
      aria-label={label}
    >
      {children}
    </tr>
  );
}

export function Cell({ children, className }: { children: ReactNode; className?: string }) {
  return <td className={clsx("px-4 py-3 align-middle", className)}>{children}</td>;
}
