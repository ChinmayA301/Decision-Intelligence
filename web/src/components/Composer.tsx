"use client";

import { useState } from "react";

interface Props {
  onSubmit: (userInput: string) => void;
}

const PLACEHOLDER = `Example: We're a Series B SaaS doing $14M ARR. We've had 3 customers ask about an enterprise tier with SOC 2, SSO, audit logs. Sales thinks we should build it. Engineering says it'll cost a quarter of roadmap. CEO is leaning yes. We have 14 months of runway.

What's the decision, what are the realistic alternatives, and what would success look like in 12–18 months?`;

export default function Composer({ onSubmit }: Props) {
  const [value, setValue] = useState("");
  const wordCount = value.trim().split(/\s+/).filter(Boolean).length;
  const isReady = wordCount >= 30;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (isReady) onSubmit(value.trim());
      }}
    >
      <textarea
        className="w-full h-56 p-4 border border-gray-300 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        placeholder={PLACEHOLDER}
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <div className="mt-3 flex items-center justify-between">
        <span className={`text-xs ${isReady ? "text-gray-400" : "text-amber-500"}`}>
          {isReady
            ? `${wordCount} words — ready to analyze`
            : `${wordCount}/30 words minimum`}
        </span>
        <button
          type="submit"
          disabled={!isReady}
          className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:bg-blue-700 transition-colors"
        >
          Generate Brief →
        </button>
      </div>
      <p className="mt-3 text-xs text-gray-400">
        This tool is for business strategy decisions only. It is not legal, financial, or personal
        advice. Share links are public.
      </p>
    </form>
  );
}
