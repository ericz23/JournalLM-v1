import type { ReactNode } from "react";

type Props = { children: ReactNode };

export default function InsightLine({ children }: Props) {
  if (!children) return null;
  return (
    <p className="mt-1 mb-3 text-xs italic text-[var(--color-brand-text-dim)]">
      {children}
    </p>
  );
}
