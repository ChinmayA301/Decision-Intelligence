"use client";

import { DecisionBrief, LensCritique, RetrievedCase } from "@/types/api";

interface Props {
  brief: DecisionBrief;
  /** Omitted on server-rendered shared pages — the button then links home. */
  onNewDecision?: () => void;
}

const VERDICT_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  endorses: { bg: "bg-green-50", text: "text-green-700", label: "Endorses" },
  endorses_with_caveats: { bg: "bg-yellow-50", text: "text-yellow-700", label: "Endorses with caveats" },
  rejects: { bg: "bg-red-50", text: "text-red-700", label: "Rejects" },
  abstains: { bg: "bg-gray-50", text: "text-gray-500", label: "Abstains" },
};

const OUTCOME_STYLES: Record<string, string> = {
  success: "bg-green-100 text-green-700",
  mixed: "bg-yellow-100 text-yellow-700",
  failure: "bg-red-100 text-red-700",
  too_early: "bg-gray-100 text-gray-600",
};

function LensCard({ critique }: { critique: LensCritique }) {
  const style = VERDICT_STYLES[critique.verdict] ?? VERDICT_STYLES.abstains;
  return (
    <div className={`rounded-lg border p-5 ${style.bg}`}>
      <div className="flex items-center justify-between mb-3">
        <span className="font-semibold text-sm text-gray-800">{critique.lens_display_name}</span>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${style.text} border border-current`}>
          {style.label}
        </span>
      </div>
      <p className="text-sm text-gray-700 mb-4 leading-relaxed">{critique.reasoning}</p>
      {critique.key_questions.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            Before deciding, answer
          </p>
          <ul className="space-y-1">
            {critique.key_questions.map((q, i) => (
              <li key={i} className="text-sm text-gray-700 flex gap-2">
                <span className="text-gray-400 flex-none">→</span>
                <span>{q}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function CaseRow({ c }: { c: RetrievedCase }) {
  return (
    <div className="flex items-start gap-4 py-3 border-b border-gray-100 last:border-0">
      <div className="flex-none text-xs text-gray-400 font-mono pt-0.5">{c.year}</div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-800 leading-snug">{c.title}</p>
        <p className="text-xs text-gray-400 mt-0.5">{c.organization} · {c.decision_maker}</p>
      </div>
      <span className={`flex-none text-xs px-2 py-0.5 rounded-full font-medium ${OUTCOME_STYLES[c.outcome_label]}`}>
        {c.outcome_label.replace("_", " ")}
      </span>
    </div>
  );
}

function BaseRateBar({ brief }: { brief: DecisionBrief }) {
  const { base_rate } = brief.reference_class;
  const decided = base_rate.success + base_rate.mixed + base_rate.failure;
  if (decided === 0) return null;
  const sW = (base_rate.success / decided) * 100;
  const mW = (base_rate.mixed / decided) * 100;
  const fW = (base_rate.failure / decided) * 100;

  return (
    <div className="mb-4">
      <div className="flex h-2 rounded-full overflow-hidden gap-0.5">
        <div className="bg-green-400 rounded-l-full" style={{ width: `${sW}%` }} />
        <div className="bg-yellow-400" style={{ width: `${mW}%` }} />
        <div className="bg-red-400 rounded-r-full" style={{ width: `${fW}%` }} />
      </div>
      <div className="flex gap-4 mt-1 text-xs text-gray-500">
        <span>{Math.round(sW)}% success ({base_rate.success})</span>
        <span>{Math.round(mW)}% mixed ({base_rate.mixed})</span>
        <span>{Math.round(fW)}% failure ({base_rate.failure})</span>
        {base_rate.too_early > 0 && <span>+{base_rate.too_early} too early</span>}
      </div>
    </div>
  );
}

export default function BriefViewer({ brief, onNewDecision }: Props) {
  const shareUrl = typeof window !== "undefined"
    ? `${window.location.origin}/briefs/${brief.brief_id}`
    : "";

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900 leading-snug">
            {brief.framed_decision.choice_being_made}
          </h1>
          <div className="flex gap-2 mt-2 flex-wrap">
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-medium">
              {brief.framed_decision.domain}
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
              {brief.framed_decision.decision_type.replace("_", " ")}
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
              {brief.framed_decision.time_horizon_months}mo horizon
            </span>
          </div>
        </div>
        {onNewDecision ? (
          <button
            onClick={onNewDecision}
            className="flex-none text-xs px-3 py-1.5 border border-gray-200 rounded hover:bg-gray-50 text-gray-600"
          >
            New decision
          </button>
        ) : (
          <a
            href="/"
            className="flex-none text-xs px-3 py-1.5 border border-gray-200 rounded hover:bg-gray-50 text-gray-600"
          >
            New decision
          </a>
        )}
      </div>

      {/* Calibration warnings */}
      {brief.calibration_notes.length > 0 && (
        <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800 space-y-1">
          {brief.calibration_notes.map((note, i) => (
            <p key={i}>⚠ {note}</p>
          ))}
        </div>
      )}

      {/* Framing */}
      <section>
        <h2 className="section-heading">How we framed it</h2>
        <p className="text-sm text-gray-600 mb-3">{brief.framed_decision.context_summary}</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Alternatives</p>
            <ul className="text-sm text-gray-700 space-y-1">
              {brief.framed_decision.alternatives.map((a, i) => (
                <li key={i} className="flex gap-2"><span className="text-gray-400">·</span>{a}</li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Key uncertainties</p>
            <ul className="text-sm text-gray-700 space-y-1">
              {brief.framed_decision.key_uncertainties.map((u, i) => (
                <li key={i} className="flex gap-2"><span className="text-gray-400">·</span>{u}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* Reference class */}
      <section>
        <h2 className="section-heading">Reference class ({brief.reference_class.base_rate.n} cases)</h2>
        {brief.reference_class.weak_reference_class && (
          <p className="text-xs text-amber-600 mb-2">
            Small reference class — treat base rates with caution.
          </p>
        )}
        <BaseRateBar brief={brief} />
        <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
          {brief.reference_class.cases.map((c) => (
            <CaseRow key={c.case_id} c={c} />
          ))}
        </div>
      </section>

      {/* Expert lenses */}
      <section>
        <h2 className="section-heading">Expert lens analysis</h2>
        {brief.tension_summary && (
          <p className="text-sm text-gray-600 italic mb-4 border-l-2 border-blue-200 pl-3">
            {brief.tension_summary}
          </p>
        )}
        <div className="space-y-4">
          {brief.lens_critiques.map((c) => (
            <LensCard key={c.lens_id} critique={c} />
          ))}
        </div>
      </section>

      {/* Pre-mortem */}
      {brief.pre_mortem.length > 0 && (
        <section>
          <h2 className="section-heading">Pre-mortem — how this goes wrong</h2>
          <ul className="space-y-2">
            {brief.pre_mortem.map((item, i) => (
              <li key={i} className="flex gap-3 text-sm text-gray-700">
                <span className="flex-none text-red-400 mt-0.5">✗</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Share */}
      <div className="pt-4 border-t border-gray-200 flex items-center gap-3">
        <span className="text-xs text-gray-400">Share this brief:</span>
        <code className="text-xs bg-gray-100 px-2 py-1 rounded text-gray-600 select-all">
          {shareUrl}
        </code>
      </div>
    </div>
  );
}
