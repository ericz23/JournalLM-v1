import { Suspense } from "react";
import InboxLayout from "@/components/inbox/InboxLayout";

export const metadata = {
  title: "Entity Inbox — JournalLM",
};

export default function InboxPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto w-full max-w-6xl px-6 py-8">
          <p className="text-[12px] italic text-[var(--color-brand-muted)]">
            Loading inbox…
          </p>
        </div>
      }
    >
      <InboxLayout />
    </Suspense>
  );
}
