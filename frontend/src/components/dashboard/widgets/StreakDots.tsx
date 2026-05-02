type Props = {
  sequence: boolean[];
  activeColor: string;
  label?: string;
};

export default function StreakDots({ sequence, activeColor, label }: Props) {
  const filledCount = sequence.filter(Boolean).length;
  const ariaLabel = label ?? `streak: ${filledCount} of ${sequence.length} days`;

  return (
    <div role="img" aria-label={ariaLabel} className="flex items-center gap-1">
      {sequence.map((active, i) => (
        <div
          key={i}
          className="h-1.5 w-1.5 rounded-full"
          style={
            active
              ? { backgroundColor: activeColor }
              : { border: `1px solid var(--color-brand-border)` }
          }
        />
      ))}
    </div>
  );
}
