"use client";

import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { format, parseISO } from "date-fns";
import { Button } from "@/components/ui/button";
import { PaperReadPreview } from "@/components/paper-read-preview";
import { SummaryText } from "@/components/summary-text";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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
  CalendarIcon,
  ThumbsUp,
  ThumbsDown,
} from "lucide-react";
import type { DailySearchSummary, Job, Paper, PaperMatch, ClaimFilterResult } from "@/lib/api";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type MatchGroup = { name: string; matches: PaperMatch[] };

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

export function DailyHeader({
  selectedDate,
  dateCount,
  dateBreakdown,
  minDate,
  maxDate,
  hasSelectedDate,
  availableDateSet,
  onDateChange,
  showRunSearch = false,
  isRunning = false,
  isCreating = false,
  onRunSearch,
}: {
  selectedDate: string;
  dateCount?: number;
  dateBreakdown?: Record<string, number>;
  minDate?: string;
  maxDate?: string;
  hasSelectedDate: boolean;
  availableDateSet: Set<string>;
  onDateChange: (value: string) => void;
  showRunSearch?: boolean;
  isRunning?: boolean;
  isCreating?: boolean;
  onRunSearch?: () => void;
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <h1 className="text-2xl font-semibold tracking-tight">Daily</h1>
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
        {showRunSearch && onRunSearch && (
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
        )}
      </div>
    </div>
  );
}

export function SearchProgress({
  job,
  progressPercent,
  matchCount,
  isCreating,
  isSummarizing = false,
}: {
  job?: Job | null;
  progressPercent: number;
  matchCount: number;
  isCreating: boolean;
  isSummarizing?: boolean;
}) {
  const status = job?.status || (isCreating ? "queued" : "running");
  const title = isSummarizing
    ? "Generating Summary"
    : status === "queued" || isCreating
      ? "Daily Search Queued"
      : "Daily Search Running";
  const message = isSummarizing
    ? "Writing daily summary…"
    : matchCount > 0
      ? `${matchCount} matches found so far`
      : status === "queued" || isCreating
        ? "Waiting to start…"
        : "Searching items…";

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-lg">{title}</CardTitle>
          <Badge variant="secondary">{status}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <div className="mb-2 flex items-center justify-between gap-3 text-sm">
            <span className="text-muted-foreground">{message}</span>
            <span className="font-medium tabular-nums">{progressPercent}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-[width]"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

      </CardContent>
    </Card>
  );
}

export function DailySummary({
  summary,
  matches,
}: {
  summary: DailySearchSummary;
  matches: PaperMatch[];
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Daily Summary</CardTitle>
      </CardHeader>
      <CardContent>
        <SummaryText
          summary={summary.summary}
          citations={summary.citations}
          matches={matches}
          className="max-w-none whitespace-pre-wrap text-base leading-7 text-foreground"
        />
      </CardContent>
    </Card>
  );
}

export function MatchesSection({
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

function MatchResultDisplay({ match }: { match: PaperMatch }) {
  const result = match.result;
  if (!result || typeof result !== "object") return null;

  const isClaim = match.filter_mode === "claim" && "verdict" in result;

  if (isClaim) {
    const claimResult = result as ClaimFilterResult;
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <Badge variant={claimResult.verdict === "positive" ? "default" : "destructive"} className="text-xs">
            {claimResult.verdict}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">{claimResult.reason}</p>
        {claimResult.evidence && (
          <p className="text-xs text-muted-foreground italic">{claimResult.evidence}</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <p className="text-sm text-muted-foreground">{result.reason}</p>
      {result.evidence && (
        <p className="text-xs text-muted-foreground italic">{result.evidence}</p>
      )}
    </div>
  );
}

function FeedbackButtons({ matchId }: { matchId: string }) {
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  const [pending, setPending] = useState<"up" | "down" | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleFeedback = (value: "up" | "down") => {
    if (submitted) return;
    setPending(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setSubmitted(true);
      try {
        await api.submitMatchFeedback(matchId, value);
        setFeedback(value);
      } catch {
        setSubmitted(false);
      }
      setPending(null);
    }, 2500);
  };

  const active = pending ?? feedback;

  return (
    <div className="flex items-center gap-1">
      {submitted && !feedback && (
        <Loader2 className="size-3 animate-spin text-muted-foreground" />
      )}
      <button
        onClick={() => handleFeedback("up")}
        disabled={submitted}
        className={`p-1 rounded hover:bg-muted ${active === "up" ? "text-green-600" : "text-muted-foreground"} ${submitted ? "opacity-50 cursor-not-allowed" : ""}`}
        aria-label="Thumbs up"
      >
        <ThumbsUp className="size-3.5" />
      </button>
      <button
        onClick={() => handleFeedback("down")}
        disabled={submitted}
        className={`p-1 rounded hover:bg-muted ${active === "down" ? "text-red-600" : "text-muted-foreground"} ${submitted ? "opacity-50 cursor-not-allowed" : ""}`}
        aria-label="Thumbs down"
      >
        <ThumbsDown className="size-3.5" />
      </button>
    </div>
  );
}

function PaperMatchCard({ match }: { match: PaperMatch }) {
  const externalUrl =
    match.paper_source_url ||
    (match.paper_source_type === "arxiv" && match.paper_source_id
      ? `https://arxiv.org/abs/${match.paper_source_id}`
      : undefined);
  const externalLabel =
    match.paper_source_type === "lesswrong"
      ? "Open on LessWrong"
      : match.paper_source_type === "arxiv" && match.paper_source_id
        ? `Open ${match.paper_source_id} on arXiv`
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
        <FeedbackButtons matchId={match.id} />
      </div>
      <MatchResultDisplay match={match} />
      {match.paper_authors && match.paper_authors.length > 0 && (
        <p className="text-sm text-muted-foreground">
          {match.paper_authors.join(", ")}
        </p>
      )}
    </div>
  );
}

function AllPaperCard({
  paper,
  isSelected,
  onSelect,
}: {
  paper: Paper;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const [liked, setLiked] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleLike = async (event: React.MouseEvent) => {
    event.stopPropagation();
    if (liked || submitting) return;
    setSubmitting(true);
    try {
      await api.submitPaperFeedback(paper.id);
      setLiked(true);
    } catch {
      // ignore
    } finally {
      setSubmitting(false);
    }
  };

  const externalUrl =
    paper.source_url ||
    (paper.source_type === "arxiv" && paper.source_id
      ? `https://arxiv.org/abs/${paper.source_id}`
      : undefined);

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full rounded-lg border p-3 space-y-1 text-left transition-colors hover:bg-muted/50",
        isSelected && "border-primary bg-muted/50 ring-1 ring-primary"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <span className="text-sm font-medium">{paper.title}</span>
          {paper.authors && paper.authors.length > 0 && (
            <p className="text-xs text-muted-foreground truncate mt-0.5">
              {paper.authors.join(", ")}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {externalUrl && (
            <a
              href={externalUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(event) => event.stopPropagation()}
              className="p-1 text-muted-foreground hover:text-foreground"
            >
              <ExternalLink className="size-3" />
            </a>
          )}
          <span
            role="button"
            tabIndex={0}
            onClick={handleLike}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                void handleLike(event as unknown as React.MouseEvent);
              }
            }}
            className={`p-1 rounded hover:bg-muted ${liked ? "text-green-600" : "text-muted-foreground"} ${liked ? "opacity-50 cursor-not-allowed" : ""}`}
            aria-label="Thumbs up"
          >
            {submitting ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <ThumbsUp className="size-3.5" />
            )}
          </span>
        </div>
      </div>
    </button>
  );
}

export function DailyAllPapersContent({
  selectedDate,
  selectedPaperId,
  onSelectPaper,
  onClosePreview,
}: {
  selectedDate: string;
  selectedPaperId: string | null;
  onSelectPaper: (paperId: string) => void;
  onClosePreview: () => void;
}) {
  const [page, setPage] = useState(1);

  const { data, isLoading: loading } = useQuery({
    queryKey: ["dailyPapers", selectedDate, page],
    queryFn: () => api.getDailyPapers(selectedDate, page),
  });

  const totalPages = data ? Math.ceil(data.total / 20) : 0;

  return (
    <div
      className={cn(
        "flex w-full flex-col gap-6 lg:flex-row",
        !selectedPaperId && "mx-auto max-w-2xl"
      )}
    >
      <div
        className={cn(
          "min-w-0 space-y-3",
          selectedPaperId ? "w-full lg:w-2/5 lg:max-w-md" : "w-full"
        )}
      >
        {loading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Loading papers...
          </div>
        )}
        {data && !loading && data.papers.length === 0 && (
          <p className="text-sm text-muted-foreground">No papers found for this date.</p>
        )}
        {data && !loading && data.papers.map((paper) => (
          <AllPaperCard
            key={paper.id}
            paper={paper}
            isSelected={selectedPaperId === paper.id}
            onSelect={() => onSelectPaper(paper.id)}
          />
        ))}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2 pt-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1 || loading}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages || loading}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        )}
      </div>
      {selectedPaperId && (
        <PaperReadPreview paperId={selectedPaperId} onClose={onClosePreview} />
      )}
    </div>
  );
}
