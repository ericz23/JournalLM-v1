import type { ReactNode } from "react";

type Props = {
  icon: ReactNode;
  title: string;
  subtitle?: ReactNode;
};

export default function EmptyState({ icon, title, subtitle }: Props) {
  return (
    <div className="flex flex-col items-center justify-center py-8 gap-2">
      <div className="flex h-8 w-8 items-center justify-center text-[var(--color-brand-muted)]">
        {icon}
      </div>
      <p className="text-[13px] font-medium text-[var(--color-brand-text-dim)]">{title}</p>
      {subtitle && (
        <p className="text-[11px] text-[var(--color-brand-muted)] text-center max-w-[200px]">
          {subtitle}
        </p>
      )}
    </div>
  );
}
