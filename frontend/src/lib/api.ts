const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const isFormData = options?.body instanceof FormData;
  const res = await fetch(`${API_URL}${path}`, {
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...options?.headers,
    },
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
  mode?: "claim" | "topic";
}

export interface ProposedFilter {
  id: string;
  name: string;
  description: string;
  mode?: "claim" | "topic";
}

export interface FilterResponse {
  id: string;
  name: string;
  definition: FilterDefinition;
  status: string;
  source: string;
  parent_filter_id?: string | null;
  proposed_action?: string | null;
  target_filter_id?: string | null;
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
  job_id?: string | null;
  status: string;
  input_text: string;
  proposed_filters: ProposedFilter[];
  error?: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
}

export interface JobProgress {
  current?: number;
  total?: number;
  [key: string]: unknown;
}

export interface Job {
  id: string;
  kind: string;
  status: string;
  subject_type?: string | null;
  subject_id?: string | null;
  queue_name?: string | null;
  progress: JobProgress;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
}

export interface JobStartResponse {
  job_id: string;
}

export interface JobOverviewEntry {
  job: Job;
  href?: string | null;
}

export interface JobsOverview {
  active: JobOverviewEntry[];
  recent: JobOverviewEntry[];
}

export interface DocumentResponse {
  id: string;
  job_id?: string | null;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  page_count: number;
  storage_path: string;
  extracted_text_path?: string | null;
  summary?: string | null;
  status: string;
  error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentUploadResponse extends DocumentResponse {
  job_id: string;
}

export interface SearchRun {
  id: string;
  job_id?: string | null;
  summary_job_id?: string | null;
  status: string;
  run_date: string;
  candidate_count?: number;
  candidate_counts?: Record<string, number>;
  match_count?: number;
  started_at?: string;
  completed_at?: string;
  error?: string;
  created_at: string;
}

export interface DailySearchSummary {
  search_run_id: string;
  summary: string;
  citations: SummaryCitation[];
}

export interface DailyCandidateCount {
  date: string;
  count: number;
  counts_by_source: Record<string, number>;
}

export interface SummaryCitation {
  paperMatchId?: string;
  arxivId?: string;
  itemId?: string;
  sourceType?: string;
  sourceId?: string;
  citedFor: string;
}

export interface ClaimFilterResult {
  verdict: "positive" | "negative";
  reason: string;
  evidence?: string;
}

export interface TopicFilterResult {
  reason: string;
  evidence?: string;
}

export interface PaperMatch {
  id: string;
  search_run_id: string;
  filter_id: string;
  paper_id: string;
  result: ClaimFilterResult | TopicFilterResult;
  filter_mode?: string | null;
  llm_model?: string;
  created_at: string;
  paper_title?: string;
  paper_authors?: string[];
  paper_source_type?: string;
  paper_source_id?: string;
  paper_source_url?: string;
  paper_item_label?: string;
  paper_search_text?: string;
  filter_name?: string;
}

export interface PaperMatchFeedback {
  id: string;
  paper_match_id: string;
  value: "up" | "down";
  created_at: string;
}

export interface PaperNote {
  id: string;
  paper_id: string;
  text: string;
  created_at: string;
  updated_at: string;
}

export interface DailySchedule {
  time: string | null;
  enabled: boolean;
}

export interface ScholarVerifyResponse {
  author_id: string;
  name: string;
  affiliations: string[];
  paper_count: number | null;
  h_index: number | null;
}

export interface ScholarImportResponse {
  id: string;
  job_id: string;
}

export interface ScholarImportStatus {
  id: string;
  status: string;
  display_name?: string;
  error?: string;
}

export interface FeedbackStatus {
  pending_votes: number;
  pending_notes: number;
  pending_proposals: number;
}

export interface FeedbackItem {
  id: string;
  kind: "vote" | "note";
  paper_id: string;
  paper_title: string;
  paper_match_id?: string | null;
  filter_id?: string | null;
  filter_name?: string | null;
  value?: "up" | "down" | null;
  text?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaginatedPapers {
  papers: Paper[];
  total: number;
  page: number;
  per_page: number;
}

export interface Paper {
  id: string;
  source_type: string;
  source_id?: string;
  title: string;
  search_text: string;
  authors: string[];
  published_at?: string;
  html_url?: string;
  source_url?: string;
  created_at: string;
}

export interface DataSource {
  source_type: string;
  name: string;
  enabled: boolean;
  settings: Record<string, unknown>;
}

export interface IdeaMapWarrant {
  id: string;
  text: string;
  citation: {
    startBlockId: string;
    endBlockId: string;
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
  job_id?: string | null;
  paper_id: string;
  status: string;
  claims: IdeaMapClaim[];
  source_url?: string;
  dropped_reason?: string;
  error?: string;
  created_at: string;
  updated_at: string;
}

export interface DailySearchJobResponse {
  job: Job;
  subject: SearchRun;
  items: PaperMatch[];
  next_cursor?: string | null;
  done: boolean;
}

export interface DailySearchSummaryJobResponse {
  job: Job;
  run: SearchRun;
  summary: DailySearchSummary | null;
  done: boolean;
}

export interface IdeaMapJobResponse {
  job: Job;
  subject: IdeaMap;
  items: Record<string, unknown>[];
  next_cursor?: string | null;
  done: boolean;
}

export interface OnboardingGenerationJobResponse {
  job: Job;
  subject: Job;
  items: FilterResponse[];
  next_cursor?: string | null;
  done: boolean;
}

export interface OnboardingExtractionJobResponse {
  job: Job;
  subject: OnboardingExtraction;
  items: Record<string, unknown>[];
  next_cursor?: string | null;
  done: boolean;
}

export interface DocumentProcessingJobResponse {
  job: Job;
  subject: DocumentResponse;
  items: Record<string, unknown>[];
  next_cursor?: string | null;
  done: boolean;
}

// API functions
export const api = {
  // Health
  health: () => fetchApi<{ status: string }>("/health"),

  // Jobs
  getJobsOverview: () => fetchApi<JobsOverview>("/jobs/overview"),
  getJob: (id: string) => fetchApi<Job>(`/jobs/${id}`),
  getDailySearchJob: (id: string, cursor?: string | null) =>
    fetchApi<DailySearchJobResponse>(
      `/search-runs/jobs/${id}${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`
    ),
  getDailySearchSummaryJob: (id: string) =>
    fetchApi<DailySearchSummaryJobResponse>(`/search-runs/summary-jobs/${id}`),
  getIdeaMapJob: (id: string) =>
    fetchApi<IdeaMapJobResponse>(`/papers/idea-map/jobs/${id}`),
  getOnboardingGenerationJob: (id: string, cursor?: string | null) =>
    fetchApi<OnboardingGenerationJobResponse>(
      `/onboarding/generations/jobs/${id}${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`
    ),
  getOnboardingExtractionJob: (id: string) =>
    fetchApi<OnboardingExtractionJobResponse>(`/onboarding/extractions/jobs/${id}`),
  getDocumentProcessingJob: (id: string) =>
    fetchApi<DocumentProcessingJobResponse>(`/documents/jobs/${id}`),

  // Onboarding
  getOnboardingStatus: () => fetchApi<OnboardingStatus>("/onboarding/status"),
  createOnboardingGeneration: (input: { input_text: string; document_ids: string[] }) =>
    fetchApi<JobStartResponse>("/onboarding/generations", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  promoteDraftFilters: (filter_ids: string[]) =>
    fetchApi<FilterResponse[]>("/onboarding/draft-filters/promote", {
      method: "POST",
      body: JSON.stringify({ filter_ids }),
    }),
  createOnboardingExtraction: (input: { input_text: string }) =>
    fetchApi<JobStartResponse>("/onboarding/extractions", {
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

  // Documents
  uploadDocument: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return fetchApi<DocumentUploadResponse>("/documents", {
      method: "POST",
      body,
    });
  },
  getDocument: (id: string) => fetchApi<DocumentResponse>(`/documents/${id}`),

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

  // Data sources
  getDataSources: () => fetchApi<DataSource[]>("/settings/data-sources"),
  updateDataSource: (
    sourceType: string,
    input: { enabled?: boolean; settings?: Record<string, unknown> }
  ) =>
    fetchApi<DataSource>(`/settings/data-sources/${sourceType}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),

  // Search runs
  getSearchRuns: () => fetchApi<SearchRun[]>("/search-runs"),
  getLatestSearchRun: () => fetchApi<SearchRun | null>("/search-runs/latest"),
  getDailyCandidateCount: (runDate: string) =>
    fetchApi<DailyCandidateCount>(
      `/search-runs/daily-candidate-count?run_date=${encodeURIComponent(runDate)}`
    ),
  createDailySearchRun: (input?: { run_date?: string }) =>
    fetchApi<JobStartResponse>("/search-runs/daily", {
      method: "POST",
      body: JSON.stringify(input ?? {}),
    }),
  createDailySearchSummary: (searchRunId: string) =>
    fetchApi<JobStartResponse>(`/search-runs/${searchRunId}/summary`, {
      method: "POST",
    }),
  getSearchRun: (id: string) => fetchApi<SearchRun>(`/search-runs/${id}`),
  getSearchRunSummary: (id: string) =>
    fetchApi<DailySearchSummary>(`/search-runs/${id}/summary`),
  getSearchRunMatches: (id: string) =>
    fetchApi<PaperMatch[]>(`/search-runs/${id}/matches`),

  // Papers
  getDailyPapers: (runDate: string, page: number = 1) =>
    fetchApi<PaginatedPapers>(`/papers/daily?run_date=${encodeURIComponent(runDate)}&page=${page}&per_page=20`),
  getPaper: (id: string) => fetchApi<Paper>(`/papers/${id}`),
  getPaperHtml: (id: string) =>
    fetchApi<{ html: string | null; source_url: string | null }>(`/papers/${id}/html`),
  generatePaperIdeaMap: (paperId: string) =>
    fetchApi<JobStartResponse>(`/papers/${paperId}/idea-map`, { method: "POST" }),
  getPaperIdeaMap: (paperId: string) =>
    fetchApi<IdeaMap>(`/papers/${paperId}/idea-map`),

  // Paper notes
  getPaperNotes: (paperId: string) =>
    fetchApi<PaperNote | null>(`/papers/${paperId}/notes`),
  updatePaperNotes: (paperId: string, text: string) =>
    fetchApi<PaperNote>(`/papers/${paperId}/notes`, {
      method: "PUT",
      body: JSON.stringify({ text }),
    }),
  // Feedback
  submitMatchFeedback: (matchId: string, value: "up" | "down") =>
    fetchApi<{ id: string; paper_id: string; value: string }>(`/paper-matches/${matchId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ value }),
    }),
  submitPaperFeedback: (paperId: string) =>
    fetchApi<{ id: string; paper_id: string; value: string }>(`/papers/${paperId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ paper_id: paperId, value: "up" }),
    }),
  getFeedbackStatus: () =>
    fetchApi<FeedbackStatus>("/feedback/status"),
  getPendingFeedbackItems: () =>
    fetchApi<FeedbackItem[]>("/feedback/items?status=pending"),
  processFeedback: () =>
    fetchApi<{ job_id: string }>("/feedback/process", { method: "POST" }),

  // Filter proposals
  acceptProposal: (filterId: string) =>
    fetchApi<FilterResponse>(`/filters/${filterId}/accept`, { method: "POST" }),
  rejectProposal: (filterId: string) =>
    fetchApi<FilterResponse>(`/filters/${filterId}/reject`, { method: "POST" }),

  // Settings
  getDailySchedule: () => fetchApi<DailySchedule>("/settings/daily-schedule"),
  updateDailySchedule: (data: DailySchedule) =>
    fetchApi<DailySchedule>("/settings/daily-schedule", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // Scholar
  verifyScholarProfile: (url: string) =>
    fetchApi<ScholarVerifyResponse>("/onboarding/scholar/verify", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),
  startScholarImport: (data: { url: string; author_id: string; display_name: string }) =>
    fetchApi<ScholarImportResponse>("/onboarding/scholar/imports", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getScholarImportStatus: (importId: string) =>
    fetchApi<ScholarImportStatus>(`/onboarding/scholar/imports/${importId}`),
};
