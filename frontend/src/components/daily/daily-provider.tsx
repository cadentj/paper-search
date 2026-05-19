"use client";

import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useArchiveFilter,
  useCreateDailySearch,
  useCreateDailySearchSummary,
  useDailyCandidateCount,
  useDailySearchJob,
  useDailySearchSummaryJob,
  useLatestSearchRun,
  useSearchRun,
  useSearchRunMatches,
  useSearchRunSummary,
} from "@/hooks/use-queries";
import {
  DAILY_SEARCH_DATE_SET,
  DAILY_SEARCH_END,
  DAILY_SEARCH_START,
  DEFAULT_DAILY_SEARCH_DATE,
  isDailySearchDate,
} from "@/lib/daily-dates";
import type { DailySearchSummary, Job, PaperMatch, SearchRun } from "@/lib/api";

type MatchGroup = {
  name: string;
  mode?: string | null;
  matches: PaperMatch[];
};

const EMPTY_PAPER_MATCHES: PaperMatch[] = [];

type DailyState = {
  activeJobId: string | null;
  activeSummaryJobId: string | null;
  summaryStartedForRunId: string | null;
  expandedFilters: Set<string>;
  selectedPaperId: string | null;
  selectedDate: string;
};

type DailyAction =
  | { type: "search-started"; jobId: string }
  | { type: "summary-requested"; runId: string }
  | { type: "summary-failed"; runId: string }
  | { type: "summary-started"; jobId: string }
  | { type: "set-date"; value: string }
  | { type: "set-selected-paper"; id: string | null }
  | { type: "toggle-filter"; filterId: string };

function dailyReducer(state: DailyState, action: DailyAction): DailyState {
  switch (action.type) {
    case "search-started":
      return {
        ...state,
        activeJobId: action.jobId,
        activeSummaryJobId: null,
        summaryStartedForRunId: null,
      };
    case "summary-requested":
      return { ...state, summaryStartedForRunId: action.runId };
    case "summary-failed":
      if (state.summaryStartedForRunId !== action.runId) return state;
      return { ...state, summaryStartedForRunId: null };
    case "summary-started":
      return { ...state, activeSummaryJobId: action.jobId };
    case "set-date":
      return { ...state, selectedDate: action.value, selectedPaperId: null };
    case "set-selected-paper":
      return { ...state, selectedPaperId: action.id };
    case "toggle-filter": {
      const expandedFilters = new Set(state.expandedFilters);
      if (expandedFilters.has(action.filterId)) {
        expandedFilters.delete(action.filterId);
      } else {
        expandedFilters.add(action.filterId);
      }
      return { ...state, expandedFilters };
    }
  }
}

type DailyContextValue = {
  effectiveSelectedDate: string;
  selectedDateCount?: number;
  selectedDateBreakdown?: Record<string, number>;
  hasSelectedDate: boolean;
  handleDateChange: (value: string) => void;
  selectedPaperId: string | null;
  setSelectedPaperId: (id: string | null) => void;
  isRunning: boolean;
  isCreating: boolean;
  handleRunSearch: () => void;
  isJobRunning: boolean;
  isSummaryRunning: boolean;
  createSearchPending: boolean;
  activeJob: Job | null | undefined;
  summaryJob: Job | null | undefined;
  progressPercent: number;
  matches: PaperMatch[];
  summary: DailySearchSummary | null;
  run: SearchRun | null | undefined;
  matchesByFilter: Record<string, MatchGroup>;
  expandedFilters: Set<string>;
  toggleFilter: (filterId: string) => void;
  archiveFilter: ReturnType<typeof useArchiveFilter>;
};

const DailyContext = createContext<DailyContextValue | null>(null);

export function useDaily() {
  const ctx = use(DailyContext);
  if (!ctx) {
    throw new Error("useDaily must be used within DailyProvider");
  }
  return ctx;
}

export function DailyProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { data: latestRun } = useLatestSearchRun();
  const [state, dispatch] = useReducer(dailyReducer, {
    activeJobId: null,
    activeSummaryJobId: null,
    summaryStartedForRunId: null,
    expandedFilters: new Set<string>(),
    selectedPaperId: null,
    selectedDate: DEFAULT_DAILY_SEARCH_DATE,
  });

  const effectiveSelectedDate = state.selectedDate || DEFAULT_DAILY_SEARCH_DATE;
  const { data: candidateCount } = useDailyCandidateCount(effectiveSelectedDate);
  const hasSelectedDate = isDailySearchDate(effectiveSelectedDate);

  const recoveredJobId =
    latestRun?.status === "queued" || latestRun?.status === "running"
      ? latestRun.job_id || null
      : null;
  const currentJobId = state.activeJobId || recoveredJobId;
  const { data: dailyJob } = useDailySearchJob(currentJobId);
  const activeJob = dailyJob?.job ?? null;
  const typedRun = dailyJob?.subject ?? null;
  const runId = typedRun?.id || latestRun?.id || null;
  const isJobRunning =
    activeJob?.status === "queued" || activeJob?.status === "running";
  const { data: fetchedRun } = useSearchRun(runId, false);
  const run = typedRun || fetchedRun || latestRun || null;
  const recoveredSummaryJobId =
    run?.status === "running" &&
    (run.summary_job_id || latestRun?.summary_job_id)
      ? run.summary_job_id || latestRun?.summary_job_id || null
      : null;
  const currentSummaryJobId =
    state.activeSummaryJobId || recoveredSummaryJobId;
  const { data: summaryJobData } = useDailySearchSummaryJob(currentSummaryJobId);
  const { data: runSummary } = useSearchRunSummary(
    runId,
    run?.status === "completed"
  );
  const summary = summaryJobData?.summary ?? runSummary ?? null;
  const summaryJob = summaryJobData?.job ?? null;
  const isSummaryRunning =
    summaryJob?.status === "queued" || summaryJob?.status === "running";
  const { data: historicalMatches = EMPTY_PAPER_MATCHES } = useSearchRunMatches(
    currentJobId ? null : runId,
    run?.status
  );
  const matches = currentJobId ? dailyJob?.items ?? EMPTY_PAPER_MATCHES : historicalMatches;
  const createSearch = useCreateDailySearch();
  const { mutate: startSummary, isPending: isStartingSummary } =
    useCreateDailySearchSummary();
  const archiveFilter = useArchiveFilter();

  useEffect(() => {
    if (!dailyJob?.done || !runId) return;
    if (run?.status === "completed" || run?.status === "failed") return;
    if (activeJob?.status !== "completed") return;
    if (currentSummaryJobId || isStartingSummary) return;
    if (state.summaryStartedForRunId === runId) return;
    if (recoveredSummaryJobId) return;

    dispatch({ type: "summary-requested", runId });
    startSummary(runId, {
      onSuccess: (data) =>
        dispatch({ type: "summary-started", jobId: data.job_id }),
      onError: () => {
        dispatch({ type: "summary-failed", runId });
      },
    });
  }, [
    dailyJob?.done,
    runId,
    run?.status,
    activeJob?.status,
    currentSummaryJobId,
    recoveredSummaryJobId,
    state.summaryStartedForRunId,
    isStartingSummary,
    startSummary,
  ]);

  useEffect(() => {
    if (!dailyJob) return;
    if (dailyJob.done) {
      queryClient.invalidateQueries({ queryKey: ["search-runs", dailyJob.subject.id] });
      queryClient.invalidateQueries({
        queryKey: ["search-runs", dailyJob.subject.id, "matches"],
      });
      queryClient.invalidateQueries({ queryKey: ["search-runs", "latest"] });
    }
  }, [dailyJob, queryClient]);

  useEffect(() => {
    if (!summaryJobData?.done || !runId) return;
    queryClient.invalidateQueries({ queryKey: ["search-runs", runId] });
    queryClient.invalidateQueries({ queryKey: ["search-runs", runId, "matches"] });
    queryClient.invalidateQueries({ queryKey: ["search-runs", runId, "summary"] });
    queryClient.invalidateQueries({ queryKey: ["search-runs", "latest"] });
  }, [summaryJobData?.done, runId, queryClient]);

  const isRunPending = run?.status === "queued" || run?.status === "running";
  const isRunning =
    isJobRunning ||
    isSummaryRunning ||
    isStartingSummary ||
    isRunPending ||
    createSearch.isPending;
  const progressTotal = Math.max(activeJob?.progress?.total ?? 1, 1);
  const progressCurrent = Math.min(activeJob?.progress?.current ?? 0, progressTotal);
  const progressPercent = isSummaryRunning
    ? 100
    : Math.round((progressCurrent / progressTotal) * 100);

  const matchesByFilter = useMemo(
    () =>
      matches.reduce(
        (acc, match) => {
          const key = match.filter_id;
          if (!acc[key]) {
            acc[key] = {
              name: match.filter_name || "Unknown",
              mode: match.filter_mode,
              matches: [],
            };
          }
          if (!acc[key].mode && match.filter_mode) {
            acc[key].mode = match.filter_mode;
          }
          acc[key].matches.push(match);
          return acc;
        },
        {} as Record<string, MatchGroup>
      ),
    [matches]
  );

  const handleRunSearch = useCallback(() => {
    createSearch.mutate(
      { run_date: effectiveSelectedDate },
      {
        onSuccess: (data) => {
          dispatch({ type: "search-started", jobId: data.job_id });
        },
      }
    );
  }, [createSearch, effectiveSelectedDate]);

  const handleDateChange = useCallback(
    (value: string) => dispatch({ type: "set-date", value }),
    []
  );

  const setSelectedPaperId = useCallback(
    (id: string | null) => dispatch({ type: "set-selected-paper", id }),
    []
  );

  const toggleFilter = useCallback(
    (filterId: string) => dispatch({ type: "toggle-filter", filterId }),
    []
  );

  const value: DailyContextValue = useMemo(
    () => ({
      effectiveSelectedDate,
      selectedDateCount: candidateCount?.count,
      selectedDateBreakdown: candidateCount?.counts_by_source,
      hasSelectedDate,
      handleDateChange,
      selectedPaperId: state.selectedPaperId,
      setSelectedPaperId,
      isRunning,
      isCreating: createSearch.isPending,
      handleRunSearch,
      isJobRunning,
      isSummaryRunning,
      createSearchPending: createSearch.isPending,
      activeJob,
      summaryJob,
      progressPercent,
      matches,
      summary,
      run,
      matchesByFilter,
      expandedFilters: state.expandedFilters,
      toggleFilter,
      archiveFilter,
    }),
    [
      effectiveSelectedDate,
      candidateCount?.count,
      candidateCount?.counts_by_source,
      hasSelectedDate,
      handleDateChange,
      state.selectedPaperId,
      state.expandedFilters,
      setSelectedPaperId,
      isRunning,
      createSearch.isPending,
      handleRunSearch,
      isJobRunning,
      isSummaryRunning,
      activeJob,
      summaryJob,
      progressPercent,
      matches,
      summary,
      run,
      matchesByFilter,
      toggleFilter,
      archiveFilter,
    ]
  );

  return <DailyContext.Provider value={value}>{children}</DailyContext.Provider>;
}

export { DAILY_SEARCH_DATE_SET, DAILY_SEARCH_END, DAILY_SEARCH_START };
