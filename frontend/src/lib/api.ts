const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

// Types
export interface FilterDefinition {
  name: string;
  description: string;
  mode?: "warrants" | "answers" | "relevance";
}

export interface ProposedFilter {
  id: string;
  name: string;
  description: string;
  mode?: "warrants" | "answers" | "relevance";
}

export interface FilterResponse {
  id: string;
  name: string;
  definition: FilterDefinition;
  status: string;
  created_at: string;
  updated_at: string;
  archived_at?: string;
}

export interface OnboardingStatus {
  completed: boolean;
  active_filter_count: number;
}

export interface OnboardingExtraction {
  id: string;
  status: string;
  input_text: string;
  proposed_filters: ProposedFilter[];
  error?: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
}

export interface SearchRun {
  id: string;
  status: string;
  run_date: string;
  candidate_count?: number;
  match_count?: number;
  summary?: string;
  summary_citations: SummaryCitation[];
  stage: string;
  progress_current: number;
  progress_total: number;
  progress_message: string;
  progress_log: ProgressLogEntry[];
  started_at?: string;
  completed_at?: string;
  error?: string;
  created_at: string;
}

export interface ProgressLogEntry {
  at: string;
  stage: string;
  message: string;
}

export interface SummaryCitation {
  paperMatchId?: string;
  arxivId: string;
  citedFor: string;
}

export interface PaperMatch {
  id: string;
  search_run_id: string;
  filter_id: string;
  paper_id: string;
  stance: string;
  relevance_score: number;
  confidence?: number;
  rationale: string;
  matched_claims: string[];
  abstract_evidence: string[];
  llm_model?: string;
  created_at: string;
  paper_title?: string;
  paper_authors?: string[];
  paper_arxiv_id?: string;
  paper_abstract?: string;
  filter_name?: string;
}

export interface Paper {
  id: string;
  arxiv_id?: string;
  title: string;
  abstract: string;
  authors: string[];
  categories?: string[];
  published_at?: string;
  html_url?: string;
  landing_url?: string;
  created_at: string;
  updated_at: string;
}

export interface IdeaMapWarrant {
  id: string;
  text: string;
  citation: {
    blockId: string;
    quote: string;
    prefix?: string;
    suffix?: string;
    htmlAnchor: string;
    sectionTitle?: string;
  };
}

export interface IdeaMapClaim {
  id: string;
  text: string;
  warrants: IdeaMapWarrant[];
}

export interface IdeaMap {
  id: string;
  paper_id: string;
  status: string;
  claims: IdeaMapClaim[];
  source_url?: string;
  dropped_reason?: string;
  error?: string;
  created_at: string;
  updated_at: string;
}

// API functions
export const api = {
  // Health
  health: () => fetchApi<{ status: string }>("/health"),

  // Onboarding
  getOnboardingStatus: () => fetchApi<OnboardingStatus>("/onboarding/status"),
  createOnboardingExtraction: (input: { input_text: string }) =>
    fetchApi<OnboardingExtraction>("/onboarding/extractions", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  getOnboardingExtraction: (id: string) =>
    fetchApi<OnboardingExtraction>(`/onboarding/extractions/${id}`),
  completeOnboarding: (filters: object[]) =>
    fetchApi<FilterResponse[]>("/onboarding/complete", {
      method: "POST",
      body: JSON.stringify({ filters }),
    }),
  resetOnboardingDev: () =>
    fetchApi<{ status: string; deleted: Record<string, number> }>("/dev/reset-onboarding", {
      method: "POST",
    }),

  // Filters
  getFilters: (status?: string) =>
    fetchApi<FilterResponse[]>(`/filters${status ? `?status=${status}` : ""}`),
  createFilter: (input: { name: string; definition: FilterDefinition }) =>
    fetchApi<FilterResponse>("/filters", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  updateFilter: (id: string, input: { name?: string; definition?: FilterDefinition }) =>
    fetchApi<FilterResponse>(`/filters/${id}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),
  archiveFilter: (id: string) =>
    fetchApi<FilterResponse>(`/filters/${id}/archive`, { method: "POST" }),
  restoreFilter: (id: string) =>
    fetchApi<FilterResponse>(`/filters/${id}/restore`, { method: "POST" }),

  // Search runs
  getSearchRuns: () => fetchApi<SearchRun[]>("/search-runs"),
  getLatestSearchRun: () => fetchApi<SearchRun | null>("/search-runs/latest"),
  createDailySearchRun: () =>
    fetchApi<SearchRun>("/search-runs/daily", { method: "POST" }),
  getSearchRun: (id: string) => fetchApi<SearchRun>(`/search-runs/${id}`),
  getSearchRunMatches: (id: string) =>
    fetchApi<PaperMatch[]>(`/search-runs/${id}/matches`),

  // Papers
  getPaper: (id: string) => fetchApi<Paper>(`/papers/${id}`),
  getPaperHtml: (id: string) =>
    fetchApi<{ html: string | null; source_url: string | null }>(`/papers/${id}/html`),
  generatePaperIdeaMap: (paperId: string) =>
    fetchApi<IdeaMap>(`/papers/${paperId}/idea-map`, { method: "POST" }),
  getPaperIdeaMap: (paperId: string) =>
    fetchApi<IdeaMap>(`/papers/${paperId}/idea-map`),

};
