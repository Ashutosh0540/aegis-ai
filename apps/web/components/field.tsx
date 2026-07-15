import { forwardRef, InputHTMLAttributes } from "react";

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

export const Field = forwardRef<HTMLInputElement, FieldProps>(
  ({ label, error, ...inputProps }, ref) => {
    return (
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-foreground/90">{label}</span>
        <input
          ref={ref}
          {...inputProps}
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none ring-primary/50 focus:ring-2"
        />
        {error && <span className="text-xs text-red-400">{error}</span>}
      </label>
    );
  }
);

Field.displayName = "Field";
