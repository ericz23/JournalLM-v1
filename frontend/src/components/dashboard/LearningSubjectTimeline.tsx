import type { LearningSubjectTimeline as TimelineData, Sentiment } from "@/lib/api";

const SUBJECT_COLORS: Record<string, string> = {
  portuguese: "var(--color-brand-accent-green)",
  "biophilic urbanism": "var(--color-brand-accent)",
  "sustainable urban runoff management": "var(--color-brand-accent)",
  "construction vocabulary": "var(--color-brand-accent-amber)",
};

function getSubjectColor(subject: string): string {
  const lower = subject.toLowerCase();
  for (const [key, val] of Object.entries(SUBJECT_COLORS)) {
    if (lower.includes(key)) return val;
  }
  return "var(--chart-5)";
}

function formatDate(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

/** Five dots: POSITIVE→NEUTRAL→NEGATIVE, proportional to sentiment distribution. */
function SentimentDots({ distribution }: { distribution: Record<Sentiment, number> }) {
  const pos = distribution.POSITIVE ?? 0;
  const neu = distribution.NEUTRAL ?? 0;
  const neg = distribution.NEGATIVE ?? 0;
  const total = pos + neu + neg;

  const DOT_COUNT = 5;
  const dots: ("POSITIVE" | "NEUTRAL" | "NEGATIVE" | "EMPTY")[] = [];

  if (total === 0) {
    for (let i = 0; i < DOT_COUNT; i++) dots.push("EMPTY");
  } else {
    const posSlots = Math.round((pos / total) * DOT_COUNT);
    const neuSlots = Math.round((neu / total) * DOT_COUNT);
    const negSlots = DOT_COUNT - posSlots - neuSlots;
    for (let i = 0; i < posSlots; i++) dots.push("POSITIVE");
    for (let i = 0; i < Math.max(0, neuSlots); i++) dots.push("NEUTRAL");
    for (let i = 0; i < Math.max(0, negSlots); i++) dots.push("NEGATIVE");
    while (dots.length < DOT_COUNT) dots.push("EMPTY");
    while (dots.length > DOT_COUNT) dots.pop();
  }

  const DOT_COLORS: Record<string, string> = {
    POSITIVE: "var(--color-brand-accent-green)",
    NEUTRAL: "var(--color-brand-muted)",
    NEGATIVE: "var(--color-brand-accent-rose)",
  };

  return (
    <div className="flex items-center gap-1" aria-hidden="true">
      {dots.map((kind, i) =>
        kind === "EMPTY" ? (
          <div
            key={i}
            className="h-1.5 w-1.5 rounded-full"
            style={{ border: "1px solid var(--color-brand-border)" }}
          />
        ) : (
          <div
            key={i}
            className="h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: DOT_COLORS[kind] }}
          />
        )
      )}
    </div>
  );
}

type Props = { items: TimelineData[] };

export default function LearningSubjectTimeline({ items }: Props) {
  if (items.length === 0) {
    return (
      <p className="py-8 text-center text-xs text-[var(--color-brand-text-dim)]">
        No subjects logged this week.
      </p>
    );
  }

  return (
    <ul className="space-y-2.5">
      {items.map((item) => {
        const color = getSubjectColor(item.subject);
        return (
          <li
            key={item.subject}
            className="relative overflow-hidden rounded-lg bg-[var(--color-brand-bg)] px-3.5 py-3"
          >
            <div
              className="absolute left-0 top-0 bottom-0 w-[3px]"
              style={{ backgroundColor: color }}
            />
            <div className="flex items-start justify-between gap-4">
              {/* Left: subject + dots */}
              <div className="flex flex-col gap-1.5 min-w-0">
                <span className="text-sm font-medium text-[var(--color-brand-text)] truncate">
                  {item.subject}
                </span>
                <SentimentDots distribution={item.sentiment_distribution as Record<Sentiment, number>} />
              </div>
              {/* Right: count + milestone + date */}
              <div className="shrink-0 flex flex-col items-end gap-0.5 text-right">
                <span className="text-[11px] font-mono text-[var(--color-brand-text-dim)]">
                  {item.sessions_window} session{item.sessions_window !== 1 ? "s" : ""} this week
                </span>
                {item.last_milestone && (
                  <span className="text-[10px] italic text-[var(--color-brand-text-dim)] max-w-[180px] truncate">
                    last: {item.last_milestone}
                  </span>
                )}
                <span className="text-[10px] font-mono text-[var(--color-brand-muted)]">
                  {formatDate(item.last_session_date)}
                </span>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
