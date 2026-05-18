"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
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
} from "@/hooks/use-queries";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Loader2,
  Play,
  EyeOff,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  PlusCircle,
} from "lucide-react";
import type { PaperMatch, SearchRun } from "@/lib/api";

type FilterMode = "claim" | "question" | "topic";
type MatchGroup = { name: string; matches: PaperMatch[] };

const STANCE_COLORS: Record<string, string> = {
  supports: "bg-green-100 text-green-800",
  refutes: "bg-red-100 text-red-800",
  complicates: "bg-amber-100 text-amber-800",
  relevant: "bg-blue-100 text-blue-800",
};

const PROGRESS_SKELETON_KEYS = [
  "daily-progress-skeleton-1",
  "daily-progress-skeleton-2",
];
const EMPTY_PAPER_MATCHES: PaperMatch[] = [];

function DailyHeader({
  run,
  isRunning,
  isCreating,
  onRunSearch,
}: {
  run?: SearchRun | null;
  isRunning: boolean;
  isCreating: boolean;
  onRunSearch: () => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Daily</h1>
        {run && (
          <p className="text-sm text-muted-foreground">
            {run.status === "completed"
              ? `${run.match_count || 0} matches from ${run.candidate_count || 0} papers`
              : run.status === "failed"
                ? "Search failed"
                : "Search in progress…"}
          </p>
        )}
      </div>
      <Button onClick={onRunSearch} disabled={isCreating || isRunning}>
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
  run,
  progressPercent,
}: {
  run?: SearchRun | null;
  progressPercent: number;
}) {
  const progressLog = run?.progress_log ?? [];

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-lg">
            {run?.stage === "queued" ? "Daily Search Queued" : "Daily Search Running"}
          </CardTitle>
          <Badge variant="secondary">{run?.stage || "creating"}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <div className="mb-2 flex items-center justify-between gap-3 text-sm">
            <span className="text-muted-foreground">
              {run?.progress_message || "Creating daily search…"}
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
      <h2 className="text-lg font-semibold">Paper Matches</h2>
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
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STANCE_COLORS[match.stance] || "bg-gray-100 text-gray-800"}`}
            >
              {match.stance}
            </span>
            <span className="text-xs text-muted-foreground">
              Score: {match.relevance_score.toFixed(2)}
            </span>
            {match.paper_arxiv_id && (
              <a
                href={`https://arxiv.org/abs/${match.paper_arxiv_id}`}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Open ${match.paper_arxiv_id} on arXiv`}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                <ExternalLink className="size-3" />
              </a>
            )}
          </div>
        </div>
      </div>
      <p className="text-sm text-muted-foreground">{match.rationale}</p>
      {match.paper_authors && match.paper_authors.length > 0 && (
        <p className="text-sm text-muted-foreground">
          {match.paper_authors.join(", ")}
        </p>
      )}
      {match.matched_claims.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {match.matched_claims.map((claim) => (
            <Badge
              key={`${match.id}-${claim}`}
              variant="outline"
              className="text-xs"
            >
              {claim}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

export default function DailyPage() {
  const { data: latestRun } = useLatestSearchRun();
  const runId = latestRun?.id || null;
  const { data: run } = useSearchRun(runId);
  const { data: matches = EMPTY_PAPER_MATCHES } = useSearchRunMatches(
    runId,
    run?.status
  );
  const createSearch = useCreateDailySearch();
  const archiveFilter = useArchiveFilter();
  const createFilter = useCreateFilter();

  const [expandedFilters, setExpandedFilters] = useState<Set<string>>(
    new Set()
  );
  const [quickFilterText, setQuickFilterText] = useState("");
  const [quickFilterType, setQuickFilterType] = useState<FilterMode>("claim");

  const isRunning =
    run?.status === "queued" || run?.status === "running";
  const progressTotal = Math.max(run?.progress_total ?? 1, 1);
  const progressCurrent = Math.min(run?.progress_current ?? 0, progressTotal);
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
        onRunSearch={() => createSearch.mutate()}
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
        <SearchProgress run={run} progressPercent={progressPercent} />
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
