"use client";

type Props = {
  count: number;
};

export default function InboxBadge({ count }: Props) {
  if (count <= 0) return null;

  if (count > 99) {
    return (
      <span
        aria-label="Many pending inbox items"
        className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-brand-accent)]"
      />
    );
  }

  return (
    <span
      aria-label={`${count} pending inbox items`}
      className="ml-1 inline-flex min-w-[18px] items-center justify-center rounded-full bg-[var(--color-brand-accent)] px-1.5 py-0.5 font-mono text-[9px] font-semibold leading-none text-[var(--color-brand-bg)]"
    >
      {count}
    </span>
  );
}
