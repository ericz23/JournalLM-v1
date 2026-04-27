"use client";

type Tab<T extends string> = {
  id: T;
  label: string;
  destructive?: boolean;
};

type Props<T extends string> = {
  tabs: Tab<T>[];
  active: T;
  onChange: (id: T) => void;
};

export default function ActionTabs<T extends string>({ tabs, active, onChange }: Props<T>) {
  return (
    <div
      role="tablist"
      className="flex items-center gap-1 border-b border-[var(--color-brand-border)]"
    >
      {tabs.map((t) => {
        const isActive = t.id === active;
        const accent = t.destructive
          ? "var(--color-brand-accent-rose)"
          : "var(--color-brand-accent)";
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(t.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-[12px] font-medium transition-colors ${
              isActive
                ? "text-[var(--color-brand-text)]"
                : "border-transparent text-[var(--color-brand-text-dim)] hover:text-[var(--color-brand-text)]"
            }`}
            style={{ borderColor: isActive ? accent : "transparent" }}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
