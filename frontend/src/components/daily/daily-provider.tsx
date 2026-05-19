"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
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
import type { DailySearchSummary, Job, PaperMatch } from "@/lib/api";

type MatchGroup = { name: string; matches: PaperMatch[] };

const EMPTY_PAPER_MATCHES: PaperMatch[] = [];

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
  run: ReturnType<typeof useSearchRun>["data"];
  matchesByFilter: Record<string, MatchGroup>;
  expandedFilters: Set<string>;
  toggleFilter: (filterId: string) => void;
  archiveFilter: ReturnType<typeof useArchiveFilter>;
};

const DailyContext = createContext<DailyContextValue | null>(null);

export function useDaily() {
  const ctx = useContext(DailyContext);
  if (!ctx) {
    throw new Error("useDaily must be used within DailyProvider");
  }
  return ctx;
}

export function DailyProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { data: latestRun } = useLatestSearchRun();
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeSummaryJobId, setActiveSummaryJobId] = useState<string | null>(null);
  const summaryStartedForRunRef = useRef<string | null>(null);
  const [expandedFilters, setExpandedFilters] = useState<Set<string>>(new Set());
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState(DEFAULT_DAILY_SEARCH_DATE);

  const effectiveSelectedDate = selectedDate || DEFAULT_DAILY_SEARCH_DATE;
  const { data: candidateCount } = useDailyCandidateCount(effectiveSelectedDate);
  const hasSelectedDate = isDailySearchDate(effectiveSelectedDate);

  const recoveredJobId =
    latestRun?.status === "queued" || latestRun?.status === "running"
      ? latestRun.job_id || null
      : null;
  const currentJobId = activeJobId || recoveredJobId;
  const { data: dailyJob } = useDailySearchJob(currentJobId);
  const activeJob = dailyJob?.job ?? null;
  const typedRun = dailyJob?.subject ?? null;
  const runId = typedRun?.id || latestRun?.id || null;
  const isJobRunning =
    activeJob?.status === "queued" || activeJob?.status === "running";
  const { data: fetchedRun } = useSearchRun(runId, false);
  const run = typedRun || fetchedRun || latestRun || null;
  const { data: summaryJobData } = useDailySearchSummaryJob(activeSummaryJobId);
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
    if (activeSummaryJobId || isStartingSummary) return;
    if (summaryStartedForRunRef.current === runId) return;

    summaryStartedForRunRef.current = runId;
    startSummary(runId, {
      onSuccess: (data) => setActiveSummaryJobId(data.job_id),
      onError: () => {
        summaryStartedForRunRef.current = null;
      },
    });
  }, [
    dailyJob?.done,
    runId,
    run?.status,
    activeJob?.status,
    activeSummaryJobId,
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
            acc[key] = { name: match.filter_name || "Unknown", matches: [] };
          }
          acc[key].matches.push(match);
          return acc;
        },
        {} as Record<string, MatchGroup>
      ),
    [matches]
  );

  const handleRunSearch = () =>
    createSearch.mutate(
      { run_date: effectiveSelectedDate },
      {
        onSuccess: (data) => {
          setActiveJobId(data.job_id);
          setActiveSummaryJobId(null);
          summaryStartedForRunRef.current = null;
        },
      }
    );

  const handleDateChange = (value: string) => {
    setSelectedDate(value);
    setSelectedPaperId(null);
  };

  const toggleFilter = (filterId: string) => {
    setExpandedFilters((prev) => {
      const next = new Set(prev);
      if (next.has(filterId)) next.delete(filterId);
      else next.add(filterId);
      return next;
    });
  };

  const value: DailyContextValue = {
    effectiveSelectedDate,
    selectedDateCount: candidateCount?.count,
    selectedDateBreakdown: candidateCount?.counts_by_source,
    hasSelectedDate,
    handleDateChange,
    selectedPaperId,
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
    expandedFilters,
    toggleFilter,
    archiveFilter,
  };

  return <DailyContext.Provider value={value}>{children}</DailyContext.Provider>;
}

export { DAILY_SEARCH_DATE_SET, DAILY_SEARCH_END, DAILY_SEARCH_START };
