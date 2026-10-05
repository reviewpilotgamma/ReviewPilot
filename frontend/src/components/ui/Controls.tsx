import clsx from "clsx";
import type { ReactNode, SelectHTMLAttributes } from "react";

interface SegmentedOption<T extends string> {
  value: T;
  label: string;
}

interface SegmentedControlProps<T extends string> {
  label: string;
  value: T;
  options: SegmentedOption<T>[];
  onChange: (value: T) => void;
  disabled?: boolean;
}

export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
  disabled,
}: SegmentedControlProps<T>) {
  return (
    <div>
      <span className="label">{label}</span>
      <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg border border-border bg-bg/60 p-1">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={value === option.value}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={clsx(
              "rounded-md px-3 py-1.5 text-sm transition duration-150",
              value === option.value ? "bg-violet text-white" : "text-muted hover:text-text",
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

interface ToggleProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  description?: string;
  disabled?: boolean;
}

export function Toggle({ label, checked, onChange, description, disabled }: ToggleProps) {
  return (
    <div>
      <span className="label">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className="inline-flex items-center gap-3"
      >
        <span
          className={clsx(
            "relative h-6 w-11 rounded-full transition duration-150",
            checked ? "bg-emerald" : "bg-border",
          )}
        >
          <span
            className={clsx(
              "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform duration-150",
              checked ? "translate-x-5" : "translate-x-0.5",
            )}
          />
        </span>
        <span className="text-sm">{checked ? "Enabled" : "Disabled"}</span>
      </button>
      {description && <p className="mt-1 text-xs text-muted">{description}</p>}
    </div>
  );
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  children: ReactNode;
}

export function Select({ label, className, children, id, ...rest }: SelectProps) {
  const selectId = id ?? (label ? `select-${label.replace(/\s+/g, "-").toLowerCase()}` : undefined);
  return (
    <div className={className}>
      {label && (
        <label htmlFor={selectId} className="label">
          {label}
        </label>
      )}
      <select id={selectId} className="input cursor-pointer pr-8" {...rest}>
        {children}
      </select>
    </div>
  );
}

export function Chip({
  active,
  onClick,
  children,
}: {
  active?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={clsx(
        "rounded-full border px-3 py-1 text-xs font-medium transition duration-150",
        active
          ? "border-violet bg-violet-soft text-violet"
          : "border-border text-muted hover:border-violet/50 hover:text-text",
      )}
    >
      {children}
    </button>
  );
}
