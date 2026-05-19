"use client";

import { useRef } from "react";
import {
  useQuery,
  useMutation,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { api, DailySchedule, FilterDefinition, FilterResponse, PaperMatch } from "@/lib/api";

const ACTIVE_JOB_STATUSES = new Set(["queued", "running"]);

const PENDING_PROPOSAL_STATUSES = new Set([
  "pending_create",
  "pending_revision",
  "pending_deletion",
]);

export function countProposalFilters(filters: FilterResponse[]): number {
  return filters.filter(
    (filter) =>
      filter.proposed_action &&
      PENDING_PROPOSAL_STATUSES.has(filter.status)
  ).length;
}

export function getAllFiltersFromCache(qc: QueryClient): FilterResponse[] {
  const entries = qc.getQueriesData<FilterResponse[]>({ queryKey: ["filters"] });
  const byId = new Map<string, FilterResponse>();
  for (const [, filters] of entries) {
    for (const filter of filters ?? []) {
      byId.set(filter.id, filter);
    }
  }
  return Array.from(byId.values());
}

export function invalidateFeedbackCompletionQueries(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: ["feedback", "status"] }),
    qc.invalidateQueries({ queryKey: ["feedback", "items", "pending"] }),
    qc.invalidateQueries({ queryKey: ["filters"] }),
    qc.invalidateQueries({ queryKey: ["jobs", "overview"] }),
  ]);
}

export function useJobsOverview() {
  return useQuery({
    queryKey: ["jobs", "overview"],
    queryFn: api.getJobsOverview,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && data.active?.length > 0) return 2000;
      return 10_000;
    },
  });
}

export function useJob(id: string | null) {
  return useQuery({
    queryKey: ["jobs", id],
    queryFn: () => api.getJob(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status && ACTIVE_JOB_STATUSES.has(status)) return 1000;
      return false;
    },
  });
}

export function useDailySearchSummaryJob(id: string | null) {
  return useQuery({
    queryKey: ["jobs", "daily-search-summary", id],
    queryFn: () => api.getDailySearchSummaryJob(id!),
    enabled: !!id,
    refetchInterval: (query) => (query.state.data?.done ? false : 500),
  });
}

export function useDailySearchJob(id: string | null) {
  const cursorRef = useRef<string | null>(null);
  const jobIdRef = useRef<string | null>(null);
  const itemsRef = useRef<Map<string, PaperMatch>>(new Map());

  return useQuery({
    queryKey: ["jobs", "daily-search", id],
    queryFn: async () => {
      if (jobIdRef.current !== id) {
        jobIdRef.current = id;
        cursorRef.current = null;
        itemsRef.current = new Map();
      }
      const result = await api.getDailySearchJob(id!, cursorRef.current);
      result.items.forEach((item) => itemsRef.current.set(item.id, item));
      cursorRef.current = result.next_cursor ?? cursorRef.current;
      return { ...result, items: Array.from(itemsRef.current.values()) };
    },
    enabled: !!id,
    refetchInterval: (query) => (query.state.data?.done ? false : 1000),
  });
}

export function useIdeaMapJob(id: string | null) {
  return useQuery({
    queryKey: ["jobs", "idea-map", id],
    queryFn: () => api.getIdeaMapJob(id!),
    enabled: !!id,
    refetchInterval: (query) => (query.state.data?.done ? false : 1000),
  });
}

export function useOnboardingGenerationJob(
  id: string | null
) {
  const cursorRef = useRef<string | null>(null);
  const jobIdRef = useRef<string | null>(null);
  const itemsRef = useRef<Map<string, FilterResponse>>(new Map());

  return useQuery({
    queryKey: ["jobs", "onboarding-generation", id],
    queryFn: async () => {
      if (jobIdRef.current !== id) {
        jobIdRef.current = id;
        cursorRef.current = null;
        itemsRef.current = new Map();
      }
      const result = await api.getOnboardingGenerationJob(
        id!,
        cursorRef.current
      );
      result.items.forEach((item) => itemsRef.current.set(item.id, item));
      cursorRef.current = result.next_cursor ?? cursorRef.current;
      return { ...result, items: Array.from(itemsRef.current.values()) };
    },
    enabled: !!id,
    refetchInterval: (query) => (query.state.data?.done ? false : 1000),
  });
}

export function useOnboardingExtractionJob(id: string | null) {
  return useQuery({
    queryKey: ["jobs", "onboarding-extraction", id],
    queryFn: () => api.getOnboardingExtractionJob(id!),
    enabled: !!id,
    refetchInterval: (query) => (query.state.data?.done ? false : 1000),
  });
}

export function useDocumentProcessingJob(id: string | null) {
  return useQuery({
    queryKey: ["jobs", "document-processing", id],
    queryFn: () => api.getDocumentProcessingJob(id!),
    enabled: !!id,
    refetchInterval: (query) => (query.state.data?.done ? false : 1000),
  });
}

// Onboarding
export function useOnboardingStatus() {
  return useQuery({
    queryKey: ["onboarding", "status"],
    queryFn: api.getOnboardingStatus,
  });
}

export function useOnboardingExtraction(id: string | null, poll = false) {
  return useQuery({
    queryKey: ["onboarding", "extractions", id],
    queryFn: () => api.getOnboardingExtraction(id!),
    enabled: !!id,
    refetchInterval: () => (poll ? 1000 : false),
  });
}

export function useCreateExtraction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { input_text: string }) =>
      api.createOnboardingExtraction(input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

export function useCreateOnboardingGeneration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { input_text: string; document_ids: string[] }) =>
      api.createOnboardingGeneration(input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["filters", "draft"] });
    },
  });
}

export function usePromoteDraftFilters() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (filterIds: string[]) => api.promoteDraftFilters(filterIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["onboarding", "status"] });
      qc.invalidateQueries({ queryKey: ["filters"] });
    },
  });
}

export function useCompleteOnboarding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (filters: object[]) => api.completeOnboarding(filters),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["onboarding", "status"] });
      qc.invalidateQueries({ queryKey: ["filters"] });
    },
  });
}

// Documents
export function useDocument(id: string | null, poll = false) {
  return useQuery({
    queryKey: ["documents", id],
    queryFn: () => api.getDocument(id!),
    enabled: !!id,
    refetchInterval: () => (poll ? 1000 : false),
  });
}

export function useUploadDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api.uploadDocument(file),
    onSuccess: (document) => {
      qc.setQueryData(["documents", document.id], document);
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

// Filters
export function useFilters(status?: string) {
  return useQuery({
    queryKey: ["filters", status],
    queryFn: () => api.getFilters(status),
  });
}

export function useCreateFilter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { name: string; definition: FilterDefinition }) =>
      api.createFilter(input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["filters"] });
    },
  });
}

export function useUpdateFilter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      input,
    }: {
      id: string;
      input: { name?: string; definition?: FilterDefinition };
    }) => api.updateFilter(id, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["filters"] });
    },
  });
}

export function useArchiveFilter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.archiveFilter(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["filters"] });
    },
  });
}

export function useRestoreFilter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.restoreFilter(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["filters"] });
    },
  });
}

// Data sources
export function useDataSources() {
  return useQuery({
    queryKey: ["settings", "data-sources"],
    queryFn: api.getDataSources,
  });
}

export function useUpdateDataSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      sourceType,
      input,
    }: {
      sourceType: string;
      input: { enabled?: boolean; settings?: Record<string, unknown> };
    }) => api.updateDataSource(sourceType, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings", "data-sources"] });
      qc.invalidateQueries({ queryKey: ["search-runs", "daily-candidate-count"] });
    },
  });
}

export function useDailySchedule() {
  return useQuery({
    queryKey: ["settings", "daily-schedule"],
    queryFn: api.getDailySchedule,
  });
}

export function useUpdateDailySchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: DailySchedule) => api.updateDailySchedule(data),
    onSuccess: (schedule) => {
      qc.setQueryData(["settings", "daily-schedule"], schedule);
    },
  });
}

export function useFeedbackStatus() {
  return useQuery({
    queryKey: ["feedback", "status"],
    queryFn: api.getFeedbackStatus,
    refetchInterval: 10_000,
  });
}

export function usePendingFeedbackItems(enabled: boolean) {
  return useQuery({
    queryKey: ["feedback", "items", "pending"],
    queryFn: api.getPendingFeedbackItems,
    enabled,
  });
}

export function useProcessFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.processFeedback,
    onSuccess: () => {
      return Promise.all([
        qc.invalidateQueries({ queryKey: ["feedback", "status"] }),
        qc.invalidateQueries({ queryKey: ["feedback", "items", "pending"] }),
        qc.invalidateQueries({ queryKey: ["filters"] }),
        qc.invalidateQueries({ queryKey: ["jobs", "overview"] }),
      ]);
    },
  });
}

export function useSubmitMatchFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ matchId, value }: { matchId: string; value: "up" | "down" }) =>
      api.submitMatchFeedback(matchId, value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["feedback", "status"] });
      qc.invalidateQueries({ queryKey: ["feedback", "items", "pending"] });
    },
  });
}

export function useSubmitPaperFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (paperId: string) => api.submitPaperFeedback(paperId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["feedback", "status"] });
      qc.invalidateQueries({ queryKey: ["feedback", "items", "pending"] });
    },
  });
}

// Search runs
export function useSearchRuns() {
  return useQuery({
    queryKey: ["search-runs"],
    queryFn: api.getSearchRuns,
  });
}

export function useLatestSearchRun() {
  return useQuery({
    queryKey: ["search-runs", "latest"],
    queryFn: api.getLatestSearchRun,
  });
}

export function useDailyCandidateCount(runDate: string) {
  return useQuery({
    queryKey: ["search-runs", "daily-candidate-count", runDate],
    queryFn: () => api.getDailyCandidateCount(runDate),
    enabled: Boolean(runDate),
    staleTime: 5 * 60 * 1000,
  });
}

export function useSearchRun(id: string | null, poll = false) {
  return useQuery({
    queryKey: ["search-runs", id],
    queryFn: () => api.getSearchRun(id!),
    enabled: !!id,
    refetchInterval: () => (poll ? 1000 : false),
  });
}

export function useSearchRunSummary(id: string | null, enabled = false) {
  return useQuery({
    queryKey: ["search-runs", id, "summary"],
    queryFn: () => api.getSearchRunSummary(id!),
    enabled: !!id && enabled,
  });
}

export function useSearchRunMatches(
  id: string | null,
  status?: string | null
) {
  return useQuery({
    queryKey: ["search-runs", id, "matches"],
    queryFn: () => api.getSearchRunMatches(id!),
    enabled: !!id,
    refetchInterval: () => {
      if (status === "queued" || status === "running") return 2000;
      return false;
    },
  });
}

export function useCreateDailySearch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input?: { run_date?: string }) => api.createDailySearchRun(input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["search-runs"] });
      qc.invalidateQueries({ queryKey: ["search-runs", "latest"] });
    },
  });
}

export function useCreateDailySearchSummary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (searchRunId: string) => api.createDailySearchSummary(searchRunId),
    onSuccess: (_data, searchRunId) => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["search-runs", searchRunId] });
      qc.invalidateQueries({ queryKey: ["search-runs", searchRunId, "summary"] });
      qc.invalidateQueries({ queryKey: ["search-runs", "latest"] });
    },
  });
}

// Papers
export function usePaper(id: string | null) {
  return useQuery({
    queryKey: ["papers", id],
    queryFn: () => api.getPaper(id!),
    enabled: !!id,
  });
}

export function usePaperHtml(id: string | null) {
  return useQuery({
    queryKey: ["papers", id, "html"],
    queryFn: () => api.getPaperHtml(id!),
    enabled: !!id,
  });
}

export function usePaperNotes(paperId: string | null) {
  return useQuery({
    queryKey: ["papers", paperId, "notes"],
    queryFn: () => api.getPaperNotes(paperId!),
    enabled: !!paperId,
  });
}

export function useUpdatePaperNotes(paperId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => api.updatePaperNotes(paperId, text),
    onSuccess: (note) => {
      qc.setQueryData(["papers", paperId, "notes"], note);
      qc.invalidateQueries({ queryKey: ["feedback", "status"] });
    },
  });
}

export function useIdeaMap(paperId: string | null, poll = false) {
  return useQuery({
    queryKey: ["papers", paperId, "idea-map"],
    queryFn: () => api.getPaperIdeaMap(paperId!),
    enabled: !!paperId,
    retry: false,
    refetchInterval: () => (poll ? 1000 : false),
  });
}

export function useGenerateIdeaMap() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (paperId: string) => api.generatePaperIdeaMap(paperId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}
