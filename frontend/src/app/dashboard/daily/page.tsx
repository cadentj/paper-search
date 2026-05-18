"use client";

import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { format, parseISO } from "date-fns";
import { Button } from "@/components/ui/button";
import { SummaryText } from "@/components/summary-text";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useLatestSearchRun,
  useSearchRun,
  useSearchRunMatches,
  useCreateDailySearch,
  useCreateFilter,
  useArchiveFilter,
  useAvailableSearchDates,
  useJob,
} from "@/hooks/use-queries";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Loader2,
  Play,
  EyeOff,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  PlusCircle,
  CalendarIcon,
} from "lucide-react";
import type { AvailableSearchDate, Job, PaperMatch, SearchRun } from "@/lib/api";

type FilterMode = "claim" | "question" | "topic";
type MatchGroup = { name: string; matches: PaperMatch[] };

const PROGRESS_SKELETON_KEYS = [
  "daily-progress-skeleton-1",
  "daily-progress-skeleton-2",
];
const EMPTY_PAPER_MATCHES: PaperMatch[] = [];
const SOURCE_LABELS: Record<string, string> = {
  arxiv: "papers",
  lesswrong: "posts",
};

function parseIndexDate(value: string): Date {
  return parseISO(`${value}T00:00:00`);
}

function DatePicker({
  selectedDate,
  availableDateSet,
  minDate,
  maxDate,
  onDateChange,
}: {
  selectedDate: string;
  availableDateSet: Set<string>;
  minDate?: string;
  maxDate?: string;
  onDateChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const selected = selectedDate ? parseIndexDate(selectedDate) : undefined;
  const min = minDate ? parseIndexDate(minDate) : undefined;
  const max = maxDate ? parseIndexDate(maxDate) : undefined;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant="outline"
            className="h-9 w-40 justify-start text-left font-normal"
          />
        }
      >
        <CalendarIcon className="mr-2 size-4" />
        {selected ? format(selected, "MMM d, yyyy") : "Select date"}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-auto p-0">
        <Calendar
          mode="single"
          selected={selected}
          defaultMonth={selected}
          startMonth={min}
          endMonth={max}
          disabled={(date) => !availableDateSet.has(format(date, "yyyy-MM-dd"))}
          onSelect={(date) => {
            if (!date) return;
            const nextDate = format(date, "yyyy-MM-dd");
            if (!availableDateSet.has(nextDate)) return;
            onDateChange(nextDate);
            setOpen(false);
          }}
        />
      </PopoverContent>
    </Popover>
  );
}

function DailyHeader({
  run,
  isRunning,
  isCreating,
  selectedDate,
  dateCount,
  dateBreakdown,
  minDate,
  maxDate,
  hasSelectedDate,
  availableDateSet,
  onDateChange,
  onRunSearch,
}: {
  run?: SearchRun | null;
  isRunning: boolean;
  isCreating: boolean;
  selectedDate: string;
  dateCount?: number;
  dateBreakdown?: Record<string, number>;
  minDate?: string;
  maxDate?: string;
  hasSelectedDate: boolean;
  availableDateSet: Set<string>;
  onDateChange: (value: string) => void;
  onRunSearch: () => void;
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Daily</h1>
        {run && (
          <p className="text-sm text-muted-foreground">
            {run.status === "completed"
              ? `${run.match_count || 0} matches from ${run.candidate_count || 0} items`
              : run.status === "failed"
                ? "Search failed"
                : "Search in progress…"}
          </p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <DatePicker
          selectedDate={selectedDate}
          availableDateSet={availableDateSet}
          minDate={minDate}
          maxDate={maxDate}
          onDateChange={onDateChange}
        />
        {dateCount !== undefined && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger>
                <Badge variant={hasSelectedDate ? "secondary" : "destructive"}>
                  {hasSelectedDate ? `${dateCount} items` : "No date"}
                </Badge>
              </TooltipTrigger>
              {hasSelectedDate && dateBreakdown && (
                <TooltipContent>
                  <div className="space-y-0.5">
                    {Object.entries(dateBreakdown).map(([source, count]) => (
                      <div key={source}>
                        {count} {SOURCE_LABELS[source] || source}
                      </div>
                    ))}
                  </div>
                </TooltipContent>
              )}
            </Tooltip>
          </TooltipProvider>
        )}
        <Button
          onClick={onRunSearch}
          disabled={isCreating || isRunning || !hasSelectedDate}
        >
          {isRunning ? (
            <>
              <Loader2 className="mr-2 size-4 animate-spin" />
              Searching…
            </>
          ) : (
            <>
              <Play className="mr-2 size-4" />
              Run Daily Search
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

function QuickAddFilter({
  filterText,
  filterType,
  isPending,
  onFilterTextChange,
  onFilterTypeChange,
  onAddFilter,
}: {
  filterText: string;
  filterType: FilterMode;
  isPending: boolean;
  onFilterTextChange: (value: string) => void;
  onFilterTypeChange: (value: FilterMode) => void;
  onAddFilter: () => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <Select
        value={filterType}
        onValueChange={(value) => {
          if (value === "claim" || value === "question" || value === "topic") {
            onFilterTypeChange(value);
          }
        }}
      >
        <SelectTrigger className="w-28 h-9" aria-label="Filter type">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="claim">Claim</SelectItem>
          <SelectItem value="question">Question</SelectItem>
          <SelectItem value="topic">Topic</SelectItem>
        </SelectContent>
      </Select>
      <Input
        aria-label="Quick add filter"
        name="quick-filter"
        autoComplete="off"
        value={filterText}
        onChange={(event) => onFilterTextChange(event.target.value)}
        placeholder="Quick add a filter…"
        className="h-9"
        onKeyDown={(event) => event.key === "Enter" && onAddFilter()}
      />
      <Button
        variant="outline"
        size="sm"
        onClick={onAddFilter}
        disabled={!filterText.trim() || isPending}
      >
        <PlusCircle className="mr-1 size-3" />
        Add
      </Button>
    </div>
  );
}

function SearchProgress({
  job,
  progressPercent,
  isCreating,
}: {
  job?: Job | null;
  progressPercent: number;
  isCreating: boolean;
}) {
  const progress = job?.progress;
  const progressLog = progress?.log ?? [];
  const stage = progress?.stage || job?.status || "creating";
  const message = progress?.message || "Creating daily search...";

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-lg">
            {stage === "queued" || isCreating ? "Daily Search Queued" : "Daily Search Running"}
          </CardTitle>
          <Badge variant="secondary">{stage}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <div className="mb-2 flex items-center justify-between gap-3 text-sm">
            <span className="text-muted-foreground">
              {message}
            </span>
            <span className="font-medium tabular-nums">{progressPercent}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-[width]"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

        {progressLog.length > 0 ? (
          <div className="rounded-md border bg-muted/30 p-3">
            <div className="space-y-1.5">
              {progressLog.slice(-6).map((entry) => (
                <div
                  key={`${entry.at}-${entry.stage}-${entry.message}`}
                  className="flex items-start gap-2 text-xs text-muted-foreground"
                >
                  <span className="mt-1 size-1.5 shrink-0 rounded-full bg-muted-foreground/60" />
                  <span>{entry.message}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {PROGRESS_SKELETON_KEYS.map((key) => (
              <Skeleton key={key} className="h-4 w-2/3" />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function DailySummary({
  run,
  matches,
}: {
  run: SearchRun;
  matches: PaperMatch[];
}) {
  if (run.status !== "completed" || !run.summary) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Daily Summary</CardTitle>
      </CardHeader>
      <CardContent>
        <SummaryText
          summary={run.summary}
          citations={run.summary_citations}
          matches={matches}
          className="max-w-none whitespace-pre-wrap text-base leading-7 text-foreground"
        />
      </CardContent>
    </Card>
  );
}

function MatchesSection({
  matchesByFilter,
  expandedFilters,
  isArchiving,
  onToggleFilter,
  onArchiveFilter,
}: {
  matchesByFilter: Record<string, MatchGroup>;
  expandedFilters: Set<string>;
  isArchiving: boolean;
  onToggleFilter: (filterId: string) => void;
  onArchiveFilter: (filterId: string) => void;
}) {
  if (Object.keys(matchesByFilter).length === 0) return null;

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Item Matches</h2>
      {Object.entries(matchesByFilter).map(([filterId, group]) => (
        <Card key={filterId}>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <button
                type="button"
                className="flex items-center gap-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => onToggleFilter(filterId)}
                aria-expanded={expandedFilters.has(filterId)}
              >
                {expandedFilters.has(filterId) ? (
                  <ChevronDown className="size-4" />
                ) : (
                  <ChevronRight className="size-4" />
                )}
                <CardTitle className="text-base">{group.name}</CardTitle>
                <Badge variant="secondary">{group.matches.length}</Badge>
              </button>
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-muted-foreground"
                onClick={() => onArchiveFilter(filterId)}
                disabled={isArchiving}
              >
                <EyeOff className="mr-1 size-3" />
                Not Interested
              </Button>
            </div>
          </CardHeader>
          {expandedFilters.has(filterId) && (
            <CardContent className="space-y-3">
              {group.matches.map((match) => (
                <PaperMatchCard key={match.id} match={match} />
              ))}
            </CardContent>
          )}
        </Card>
      ))}
    </div>
  );
}

function PaperMatchCard({ match }: { match: PaperMatch }) {
  const externalUrl =
    match.paper_source_url ||
    (match.paper_arxiv_id ? `https://arxiv.org/abs/${match.paper_arxiv_id}` : undefined);
  const externalLabel =
    match.paper_source_type === "lesswrong"
      ? "Open on LessWrong"
      : match.paper_arxiv_id
        ? `Open ${match.paper_arxiv_id} on arXiv`
        : "Open source";

  return (
    <div className="rounded-lg border p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <Link
            href={`/dashboard/papers/${match.paper_id}`}
            className="text-left text-base font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {match.paper_title}
          </Link>
          <div className="flex items-center gap-2 mt-1">
            {externalUrl && (
              <a
                href={externalUrl}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={externalLabel}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                <ExternalLink className="size-3" />
              </a>
            )}
          </div>
        </div>
      </div>
      <p className="text-sm text-muted-foreground">{match.result}</p>
      {match.paper_authors && match.paper_authors.length > 0 && (
        <p className="text-sm text-muted-foreground">
          {match.paper_authors.join(", ")}
        </p>
      )}
    </div>
  );
}

export default function DailyPage() {
  const queryClient = useQueryClient();
  const { data: latestRun } = useLatestSearchRun();
  const { data: availableDates } = useAvailableSearchDates();
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const { data: activeJob } = useJob(activeJobId);
  const activeRunId =
    activeJob?.subject_type === "search_run" ? activeJob.subject_id || null : null;
  const runId = activeRunId || latestRun?.id || null;
  const isJobRunning =
    activeJob?.status === "queued" || activeJob?.status === "running";
  const { data: run } = useSearchRun(runId, !!activeRunId && !!isJobRunning);
  const { data: matches = EMPTY_PAPER_MATCHES } = useSearchRunMatches(
    runId,
    activeJob?.status ?? run?.status
  );
  const createSearch = useCreateDailySearch();
  const archiveFilter = useArchiveFilter();
  const createFilter = useCreateFilter();

  const [expandedFilters, setExpandedFilters] = useState<Set<string>>(
    new Set()
  );
  const [quickFilterText, setQuickFilterText] = useState("");
  const [quickFilterType, setQuickFilterType] = useState<FilterMode>("claim");

  const indexedDateEntries = useMemo(
    () =>
      new Map<string, AvailableSearchDate>(
        (availableDates?.dates ?? []).map((entry) => [entry.date, entry])
      ),
    [availableDates]
  );
  const availableDateSet = useMemo(
    () => new Set(indexedDateEntries.keys()),
    [indexedDateEntries]
  );
  const indexedDates = availableDates?.dates.map((entry) => entry.date) ?? [];
  const minDate = indexedDates.length ? indexedDates[indexedDates.length - 1] : undefined;
  const maxDate = indexedDates.length ? indexedDates[0] : undefined;
  const [selectedDate, setSelectedDate] = useState("");
  const effectiveSelectedDate = selectedDate || availableDates?.default_date || "";

  const selectedDateEntry = indexedDateEntries.get(effectiveSelectedDate);
  const selectedDateCount = selectedDateEntry?.total_count ?? selectedDateEntry?.count;
  const selectedDateBreakdown = selectedDateEntry?.counts_by_source;
  const hasSelectedDate = selectedDateEntry !== undefined;

  useEffect(() => {
    if (!activeJob || activeJob.status === "queued" || activeJob.status === "running") {
      return;
    }
    if (activeRunId) {
      queryClient.invalidateQueries({ queryKey: ["search-runs", activeRunId] });
      queryClient.invalidateQueries({ queryKey: ["search-runs", activeRunId, "matches"] });
      queryClient.invalidateQueries({ queryKey: ["search-runs", "latest"] });
    }
  }, [activeJob, activeRunId, queryClient]);

  const isRunning = isJobRunning || createSearch.isPending;
  const progressTotal = Math.max(activeJob?.progress?.total ?? 1, 1);
  const progressCurrent = Math.min(activeJob?.progress?.current ?? 0, progressTotal);
  const progressPercent = Math.round((progressCurrent / progressTotal) * 100);

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

  const handleQuickAddFilter = async () => {
    const text = quickFilterText.trim();
    if (!text) return;
    await createFilter.mutateAsync({
      name: text.slice(0, 60),
      definition: {
        name: text.slice(0, 60),
        description: text,
        mode: quickFilterType,
      },
    });
    setQuickFilterText("");
  };

  const toggleFilter = (filterId: string) => {
    setExpandedFilters((prev) => {
      const next = new Set(prev);
      if (next.has(filterId)) next.delete(filterId);
      else next.add(filterId);
      return next;
    });
  };

  return (
    <div className="flex-1 p-6 space-y-6 max-w-5xl">
      <DailyHeader
        run={run}
        isRunning={isRunning}
        isCreating={createSearch.isPending}
        selectedDate={effectiveSelectedDate}
        dateCount={selectedDateCount}
        dateBreakdown={selectedDateBreakdown}
        minDate={minDate}
        maxDate={maxDate}
        hasSelectedDate={hasSelectedDate}
        availableDateSet={availableDateSet}
        onDateChange={setSelectedDate}
        onRunSearch={() =>
          createSearch.mutate(
            { run_date: effectiveSelectedDate },
            {
              onSuccess: (data) => setActiveJobId(data.job_id),
            }
          )
        }
      />
      <QuickAddFilter
        filterText={quickFilterText}
        filterType={quickFilterType}
        isPending={createFilter.isPending}
        onFilterTextChange={setQuickFilterText}
        onFilterTypeChange={setQuickFilterType}
        onAddFilter={handleQuickAddFilter}
      />
      {(isRunning || createSearch.isPending) && (
        <SearchProgress
          job={activeJob}
          progressPercent={progressPercent}
          isCreating={createSearch.isPending}
        />
      )}
      {run && <DailySummary run={run} matches={matches} />}
      {run?.status === "failed" && (
        <Card className="border-destructive">
          <CardContent className="pt-4">
            <p className="text-sm text-destructive">
              {run.error || "Daily search failed. Please try again."}
            </p>
          </CardContent>
        </Card>
      )}
      <MatchesSection
        matchesByFilter={matchesByFilter}
        expandedFilters={expandedFilters}
        isArchiving={archiveFilter.isPending}
        onToggleFilter={toggleFilter}
        onArchiveFilter={(filterId) => archiveFilter.mutate(filterId)}
      />
      {run?.status === "completed" && Object.keys(matchesByFilter).length === 0 && (
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-muted-foreground">
              No matches found. Try running a daily search or adding more
              filters.
            </p>
          </CardContent>
        </Card>
      )}
      {!run && !isRunning && (
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-muted-foreground">
              No daily search has been run yet. Click &quot;Run Daily
              Search&quot; to get started.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
