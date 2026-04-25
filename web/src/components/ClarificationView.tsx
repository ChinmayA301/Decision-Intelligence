"use client";

import { ClarificationResponse } from "@/types/api";

interface Props {
  data: ClarificationResponse;
  onBack: () => void;
}

export default function ClarificationView({ data, onBack }: Props) {
  return (
    <div className="max-w-2xl">
      <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-lg">
        <p className="text-sm font-medium text-amber-800 mb-1">
          We need a bit more to work with
        </p>
        <p className="text-sm text-amber-700">{data.reason}</p>
      </div>

      <h2 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">
        Clarifying questions
      </h2>
      <ul className="space-y-3 mb-8">
        {data.clarifying_questions.map((q, i) => (
          <li key={i} className="flex gap-3 text-sm">
            <span className="flex-none font-mono text-gray-400 text-xs mt-0.5">{i + 1}.</span>
            <span className="text-gray-800">{q}</span>
          </li>
        ))}
      </ul>

      <button
        onClick={onBack}
        className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
      >
        ← Revise your decision
      </button>
    </div>
  );
}
