import type { Sentiment } from "@/lib/api";

type Props = {
  distribution: Record<Sentiment, number>;
  height?: number;
};

const COLORS: Record<Sentiment, string> = {
  POSITIVE: "var(--color-brand-accent-green)",
  NEGATIVE: "var(--color-brand-accent-rose)",
  NEUTRAL: "var(--color-brand-muted)",
};

export default function SentimentBar({ distribution, height = 4 }: Props) {
  const pos = distribution.POSITIVE ?? 0;
  const neg = distribution.NEGATIVE ?? 0;
  const neu = distribution.NEUTRAL ?? 0;
  const total = pos + neg + neu;

  const tooltip = `${pos} positive · ${neu} neutral · ${neg} negative`;

  if (total === 0) {
    return (
      <div
        title={tooltip}
        className="w-full rounded-full"
        style={{ height, backgroundColor: "var(--color-brand-border)" }}
      />
    );
  }

  const allSegments: { sentiment: Sentiment; count: number }[] = [
    { sentiment: "POSITIVE", count: pos },
    { sentiment: "NEUTRAL", count: neu },
    { sentiment: "NEGATIVE", count: neg },
  ];
  const segments = allSegments.filter((s) => s.count > 0);

  return (
    <div
      title={tooltip}
      className="flex w-full overflow-hidden rounded-full"
      style={{ height }}
    >
      {segments.map(({ sentiment, count }) => (
        <div
          key={sentiment}
          style={{
            width: `${(count / total) * 100}%`,
            backgroundColor: COLORS[sentiment],
          }}
        />
      ))}
    </div>
  );
}
