export type StarterPrompt = {
  query: string;
  icon: string;
  label: string;
};

export type ChatMode = {
  id: string;
  label: string;
  icon: string;
  accentColor: string;
  description: string;
  starterPrompts: StarterPrompt[];
  disclaimer?: string;
};

export const CHAT_MODES: ChatMode[] = [
  {
    id: "default",
    label: "Assistant",
    icon: "✦",
    accentColor: "#F0B429",
    description: "Journal-grounded Q&A",
    starterPrompts: [
      { query: "What did I do on October 3rd?", icon: "📅", label: "Recall a day" },
      { query: "Which restaurants have I visited?", icon: "🍽️", label: "Find restaurants" },
      { query: "Summarize my week of Oct 1-7", icon: "📊", label: "Weekly summary" },
      { query: "How was I feeling about work?", icon: "💭", label: "Explore feelings" },
    ],
  },
  {
    id: "therapist",
    label: "Therapist",
    icon: "🧠",
    accentColor: "#C084FC",
    description: "CBT-informed reflective support",
    starterPrompts: [
      { query: "I've been feeling stressed about work lately", icon: "😮‍💨", label: "Process stress" },
      { query: "Help me challenge a negative thought I'm having", icon: "🔄", label: "Reframe thoughts" },
      { query: "I want to reflect on my emotional patterns", icon: "📈", label: "Find patterns" },
      { query: "Guide me through a mindfulness exercise", icon: "🧘", label: "Mindfulness" },
    ],
    disclaimer: "AI companion — not a substitute for professional mental health care.",
  },
];

export const DEFAULT_MODE = CHAT_MODES[0];

export function getModeById(id: string): ChatMode {
  return CHAT_MODES.find((m) => m.id === id) ?? DEFAULT_MODE;
}
