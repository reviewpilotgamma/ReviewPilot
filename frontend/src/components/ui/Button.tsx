import clsx from "clsx";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Spinner } from "./Spinner";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-violet text-white hover:bg-violet/90 shadow-[0_0_20px_-6px_rgba(139,92,246,0.7)]",
  secondary: "border border-border bg-surface text-text hover:border-violet/60",
  ghost: "text-muted hover:bg-border/50 hover:text-text",
  danger: "border border-rose/40 bg-rose-soft text-rose hover:bg-rose/20",
};
const SIZES: Record<Size, string> = { sm: "px-3 py-1.5 text-xs", md: "px-4 py-2 text-sm" };

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  icon,
  className,
  children,
  disabled,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition duration-150 ease-out",
        "disabled:cursor-not-allowed disabled:opacity-50",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner className="h-4 w-4" /> : icon}
      {children}
    </button>
  );
}
