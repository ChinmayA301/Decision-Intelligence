export interface Citation {
  type: "book" | "article" | "filing" | "interview" | "primary_doc";
  title: string;
  author?: string;
  year: number;
  url?: string;
  pages?: string;
  quote?: string;
}

export interface RetrievedCase {
  case_id: string;
  title: string;
  year: number;
  organization: string;
  decision_maker: string;
  domain: string;
  decision_type: string;
  similarity: number;
  outcome_label: "success" | "mixed" | "failure" | "too_early";
  era_dependence: "high" | "medium" | "low";
  snippet: string;
}

export interface BaseRate {
  n: number;
  success: number;
  mixed: number;
  failure: number;
  too_early: number;
}

export interface ReferenceClass {
  cases: RetrievedCase[];
  base_rate: BaseRate;
  weak_reference_class: boolean;
}

export interface FramedDecision {
  choice_being_made: string;
  alternatives: string[];
  domain: string;
  decision_type: string;
  time_horizon_months: number;
  key_uncertainties: string[];
  constraints: string[];
  user_apparent_leaning?: string;
  context_summary: string;
}

export interface LensCritique {
  lens_id: string;
  lens_display_name: string;
  verdict: "endorses" | "endorses_with_caveats" | "rejects" | "abstains";
  reasoning: string;
  key_questions: string[];
  most_relevant_case_ids: string[];
  confidence: "low" | "medium" | "high";
}

export interface DecisionBrief {
  brief_id: string;
  framed_decision: FramedDecision;
  reference_class: ReferenceClass;
  lens_critiques: LensCritique[];
  tension_summary: string;
  pre_mortem: string[];
  cited_case_ids: string[];
  calibration_notes: string[];
  created_at: string;
}

export interface ClarificationResponse {
  type: "clarification";
  reason: string;
  clarifying_questions: string[];
}

export type BriefResponse = DecisionBrief | ClarificationResponse;

export function isClarification(r: BriefResponse): r is ClarificationResponse {
  return (r as ClarificationResponse).type === "clarification";
}
