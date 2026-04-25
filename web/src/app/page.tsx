"use client";

import { useState } from "react";
import { BriefResponse, isClarification } from "@/types/api";
import BriefViewer from "@/components/BriefViewer";
import ClarificationView from "@/components/ClarificationView";
import Composer from "@/components/Composer";

type AppState =
  | { phase: "compose" }
  | { phase: "loading" }
  | { phase: "clarification"; data: Extract<BriefResponse, { type: "clarification" }> }
  | { phase: "brief"; data: Exclude<BriefResponse, { type: string }> };

export default function Home() {
  const [appState, setAppState] = useState<AppState>({ phase: "compose" });
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(userInput: string) {
    setError(null);
    setAppState({ phase: "loading" });

    try {
      const res = await fetch("/api/briefs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_input: userInput }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Server error ${res.status}`);
      }

      const data: BriefResponse = await res.json();

      if (isClarification(data)) {
        setAppState({ phase: "clarification", data });
      } else {
        setAppState({ phase: "brief", data });
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setAppState({ phase: "compose" });
    }
  }

  function handleReset() {
    setAppState({ phase: "compose" });
    setError(null);
  }

  return (
    <div>
      {appState.phase === "compose" && (
        <>
          <div className="mb-8">
            <h1 className="text-2xl font-bold mb-2">Describe your decision</h1>
            <p className="text-gray-500 text-sm">
              Write 1–3 paragraphs about the decision you&apos;re facing. The more specific you are,
              the better the reference class match. We return a brief in 20–40 seconds.
            </p>
          </div>
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
              {error}
            </div>
          )}
          <Composer onSubmit={handleSubmit} />
        </>
      )}

      {appState.phase === "loading" && (
        <div className="text-center py-20">
          <div className="inline-block w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin mb-4" />
          <p className="text-gray-500 text-sm">
            Framing your decision, retrieving reference cases, running lens analysis…
          </p>
          <p className="text-gray-400 text-xs mt-1">Usually 20–40 seconds</p>
        </div>
      )}

      {appState.phase === "clarification" && (
        <ClarificationView data={appState.data} onBack={handleReset} />
      )}

      {appState.phase === "brief" && (
        <BriefViewer brief={appState.data} onNewDecision={handleReset} />
      )}
    </div>
  );
}
