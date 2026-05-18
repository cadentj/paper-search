"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
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
import type { PaperMatch } from "@/lib/api";

const STANCE_COLORS: Record<string, string> = {
  supports: "bg-green-100 text-green-800",
  refutes: "bg-red-100 text-red-800",
  complicates: "bg-amber-100 text-amber-800",
  relevant: "bg-blue-100 text-blue-800",
};

export default function DailyPage() {
  const router = useRouter();
  const { data: latestRun } = useLatestSearchRun();
  const runId = latestRun?.id || null;
  const { data: run } = useSearchRun(runId);
  const { data: matches } = useSearchRunMatches(runId, run?.status);
  const createSearch = useCreateDailySearch();
  const archiveFilter = useArchiveFilter();

  const [expandedFilters, setExpandedFilters] = useState<Set<string>>(
    new Set()
  );
  const [quickFilterText, setQuickFilterText] = useState("");
  const [quickFilterType, setQuickFilterType] = useState("claim");
  const createFilter = useCreateFilter();

  const isRunning =
    run?.status === "queued" || run?.status === "running";
  const progressTotal = Math.max(run?.progress_total ?? 1, 1);
  const progressCurrent = Math.min(run?.progress_current ?? 0, progressTotal);
  const progressPercent = Math.round((progressCurrent / progressTotal) * 100);
  const progressLog = run?.progress_log ?? [];

  const handleRunSearch = async () => {
    await createSearch.mutateAsync();
  };

  const handleFilterNotInterested = async (filterId: string) => {
    await archiveFilter.mutateAsync(filterId);
  };

  const matchesByFilter = (matches || []).reduce(
    (acc, m) => {
      const key = m.filter_id;
      if (!acc[key]) acc[key] = { name: m.filter_name || "Unknown", matches: [] };
      acc[key].matches.push(m);
      return acc;
    },
    {} as Record<string, { name: string; matches: PaperMatch[] }>
  );

  const handleQuickAddFilter = async () => {
    const text = quickFilterText.trim();
    if (!text) return;
    const mode = quickFilterType === "claim" ? "warrants" as const : quickFilterType === "question" ? "answers" as const : "relevance" as const;
    await createFilter.mutateAsync({
      name: text.slice(0, 60),
      definition: {
        name: text.slice(0, 60),
        description: text,
        mode,
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
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Daily</h1>
            {run && (
              <p className="text-sm text-muted-foreground">
                {run.status === "completed"
                  ? `${run.match_count || 0} matches from ${run.candidate_count || 0} papers`
                  : run.status === "failed"
                    ? "Search failed"
                    : "Search in progress..."}
              </p>
            )}
          </div>
          <Button
            onClick={handleRunSearch}
            disabled={createSearch.isPending || isRunning}
          >
            {isRunning ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                Searching...
              </>
            ) : (
              <>
                <Play className="mr-2 size-4" />
                Run Daily Search
              </>
            )}
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <Select value={quickFilterType} onValueChange={(v) => { if (v) setQuickFilterType(v); }}>
            <SelectTrigger className="w-28 h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="claim">Claim</SelectItem>
              <SelectItem value="question">Question</SelectItem>
              <SelectItem value="topic">Topic</SelectItem>
            </SelectContent>
          </Select>
          <Input
            value={quickFilterText}
            onChange={(e) => setQuickFilterText(e.target.value)}
            placeholder="Quick add a filter..."
            className="h-9"
            onKeyDown={(e) => e.key === "Enter" && handleQuickAddFilter()}
          />
          <Button
            variant="outline"
            size="sm"
            onClick={handleQuickAddFilter}
            disabled={!quickFilterText.trim() || createFilter.isPending}
          >
            <PlusCircle className="mr-1 size-3" />
            Add
          </Button>
        </div>

        {(isRunning || createSearch.isPending) && (
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="text-lg">
                  {run?.stage === "queued" ? "Daily Search Queued" : "Daily Search Running"}
                </CardTitle>
                <Badge variant="secondary">
                  {run?.stage || "creating"}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <div className="mb-2 flex items-center justify-between gap-3 text-sm">
                  <span className="text-muted-foreground">
                    {run?.progress_message || "Creating daily search..."}
                  </span>
                  <span className="font-medium tabular-nums">
                    {progressPercent}%
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
              </div>

              {progressLog.length > 0 ? (
                <div className="rounded-md border bg-muted/30 p-3">
                  <div className="space-y-1.5">
                    {progressLog.slice(-6).map((entry, i) => (
                      <div
                        key={`${entry.at}-${i}`}
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
                  <Skeleton className="h-4 w-2/3" />
                  <Skeleton className="h-4 w-1/2" />
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {run?.status === "completed" && run.summary && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Daily Summary</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="max-w-none text-base leading-7 text-foreground whitespace-pre-line">
                {run.summary}
                {run.summary_citations && run.summary_citations.length > 0 && (
                  <span className="ml-2 inline-flex flex-wrap items-center gap-1.5 align-baseline">
                    {run.summary_citations.map((c, i) => {
                      const citationMatch = (matches || []).find(
                        (match) =>
                          match.id === c.paperMatchId ||
                          match.paper_arxiv_id === c.arxivId
                      );
                      return (
                        <button
                          key={`${c.arxivId}-${i}`}
                          type="button"
                          onClick={() =>
                            citationMatch &&
                            router.push(`/dashboard/papers/${citationMatch.paper_id}`)
                          }
                          disabled={!citationMatch}
                          title={c.citedFor}
                          aria-label={`Open citation ${i + 1}: ${c.arxivId}`}
                          className="inline-flex h-6 items-center rounded-md border border-border px-2 text-xs font-medium leading-none text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground disabled:cursor-default disabled:opacity-60"
                        >
                          [{i + 1}] {c.arxivId}
                        </button>
                      );
                    })}
                  </span>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {run?.status === "failed" && (
          <Card className="border-destructive">
            <CardContent className="pt-4">
              <p className="text-sm text-destructive">
                {run.error || "Daily search failed. Please try again."}
              </p>
            </CardContent>
          </Card>
        )}

        {Object.keys(matchesByFilter).length > 0 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Paper Matches</h2>
            {Object.entries(matchesByFilter).map(([filterId, group]) => (
              <Card key={filterId}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <button
                      className="flex items-center gap-2 text-left"
                      onClick={() => toggleFilter(filterId)}
                      aria-expanded={expandedFilters.has(filterId)}
                    >
                      {expandedFilters.has(filterId) ? (
                        <ChevronDown className="size-4" />
                      ) : (
                        <ChevronRight className="size-4" />
                      )}
                      <CardTitle className="text-base">
                        {group.name}
                      </CardTitle>
                      <Badge variant="secondary">
                        {group.matches.length}
                      </Badge>
                    </button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-xs text-muted-foreground"
                      onClick={() => handleFilterNotInterested(filterId)}
                      disabled={archiveFilter.isPending}
                    >
                      <EyeOff className="mr-1 size-3" />
                      Not Interested
                    </Button>
                  </div>
                </CardHeader>
                {expandedFilters.has(filterId) && (
                  <CardContent className="space-y-3">
                    {group.matches.map((match) => (
                      <div
                        key={match.id}
                        className="rounded-lg border p-3 space-y-2"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1">
                            <button
                              className="text-base font-medium hover:underline text-left"
                              onClick={() =>
                                router.push(`/dashboard/papers/${match.paper_id}`)
                              }
                            >
                              {match.paper_title}
                            </button>
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
                                  className="text-xs text-muted-foreground hover:text-foreground"
                                >
                                  <ExternalLink className="size-3" />
                                </a>
                              )}
                            </div>
                          </div>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          {match.rationale}
                        </p>
                        {match.paper_authors &&
                          match.paper_authors.length > 0 && (
                            <p className="text-sm text-muted-foreground">
                              {match.paper_authors.join(", ")}
                            </p>
                          )}
                        {match.matched_claims.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {match.matched_claims.map((c, i) => (
                              <Badge
                                key={i}
                                variant="outline"
                                className="text-xs"
                              >
                                {c}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </CardContent>
                )}
              </Card>
            ))}
          </div>
        )}

        {run?.status === "completed" &&
          Object.keys(matchesByFilter).length === 0 && (
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
