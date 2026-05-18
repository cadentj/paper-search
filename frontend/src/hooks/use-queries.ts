"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, FilterDefinition } from "@/lib/api";

// Onboarding
export function useOnboardingStatus() {
  return useQuery({
    queryKey: ["onboarding", "status"],
    queryFn: api.getOnboardingStatus,
  });
}

export function useOnboardingExtraction(id: string | null) {
  return useQuery({
    queryKey: ["onboarding", "extractions", id],
    queryFn: () => api.getOnboardingExtraction(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "queued" || status === "running") return 1000;
      return false;
    },
  });
}

export function useCreateExtraction() {
  return useMutation({
    mutationFn: (input: { input_text: string }) =>
      api.createOnboardingExtraction(input),
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

export function useResetOnboarding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.resetOnboardingDev,
    onSuccess: () => {
      qc.invalidateQueries();
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
      ...input
    }: {
      id: string;
      name?: string;
      definition?: FilterDefinition;
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
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "queued" || status === "running") return 1000;
      return false;
    },
  });
}

export function useSearchRun(id: string | null) {
  return useQuery({
    queryKey: ["search-runs", id],
    queryFn: () => api.getSearchRun(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "queued" || status === "running") return 1000;
      return false;
    },
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
    mutationFn: api.createDailySearchRun,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["search-runs"] });
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

export function useIdeaMap(paperId: string | null) {
  return useQuery({
    queryKey: ["papers", paperId, "idea-map"],
    queryFn: () => api.getPaperIdeaMap(paperId!),
    enabled: !!paperId,
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "queued" || status === "running") return 1000;
      return false;
    },
  });
}

export function useGenerateIdeaMap() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (paperId: string) => api.generatePaperIdeaMap(paperId),
    onSuccess: (data) => {
      qc.invalidateQueries({
        queryKey: ["papers", data.paper_id, "idea-map"],
      });
    },
  });
}
