"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  useLatestSearchRun,
  useSearchRun,
  useSearchRunMatches,
  useCreateDailySearch,
  useSubmitFeedback,
} from "@/hooks/use-queries";
import {
  Loader2,
  Play,
  ThumbsUp,
  ThumbsDown,
  EyeOff,
  ExternalLink,
  ChevronDown,
  ChevronRight,
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
  const { data: matches, refetch: refetchMatches } = useSearchRunMatches(
    run?.status === "completed" ? runId : null
  );
  const createSearch = useCreateDailySearch();
  const feedback = useSubmitFeedback();

  const [expandedFilters, setExpandedFilters] = useState<Set<string>>(
    new Set()
  );

  const isRunning =
    run?.status === "queued" || run?.status === "running";

  const handleRunSearch = async () => {
    await createSearch.mutateAsync();
  };

  const handleNotInterested = async (matchId: string) => {
    await feedback.mutateAsync({
      target_type: "paper_match",
      target_id: matchId,
      value: "not_interested",
    });
    refetchMatches();
  };

  const handleFilterNotInterested = async (filterId: string) => {
    await feedback.mutateAsync({
      target_type: "filter",
      target_id: filterId,
      value: "not_interested",
    });
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

  const toggleFilter = (filterId: string) => {
    setExpandedFilters((prev) => {
      const next = new Set(prev);
      if (next.has(filterId)) next.delete(filterId);
      else next.add(filterId);
      return next;
    });
  };

  return (
    <AppShell>
      <div className="flex-1 p-6 space-y-6 max-w-4xl">
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

        {isRunning && (
          <div className="space-y-3">
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        )}

        {run?.status === "completed" && run.summary && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Daily Summary</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="prose prose-sm max-w-none text-sm leading-relaxed whitespace-pre-line">
                {run.summary}
              </div>
              {run.summary_citations && run.summary_citations.length > 0 && (
                <div className="mt-4 pt-3 border-t">
                  <p className="text-xs font-medium text-muted-foreground mb-2">
                    Citations
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {run.summary_citations.map((c, i) => (
                      <Badge
                        key={i}
                        variant="outline"
                        className="text-xs cursor-pointer hover:bg-accent"
                      >
                        {c.arxivId}: {c.citedFor}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
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

        {run?.status === "completed" && Object.keys(matchesByFilter).length > 0 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Paper Matches</h2>
            {Object.entries(matchesByFilter).map(([filterId, group]) => (
              <Card key={filterId}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <button
                      className="flex items-center gap-2 text-left"
                      onClick={() => toggleFilter(filterId)}
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
                    >
                      <EyeOff className="mr-1 size-3" />
                      Not Interested
                    </Button>
                  </div>
                </CardHeader>
                {(expandedFilters.has(filterId) || expandedFilters.size === 0) && (
                  <CardContent className="space-y-3">
                    {group.matches.map((match) => (
                      <div
                        key={match.id}
                        className="rounded-lg border p-3 space-y-2"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1">
                            <button
                              className="text-sm font-medium hover:underline text-left"
                              onClick={() =>
                                router.push(`/papers/${match.paper_id}`)
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
                          <div className="flex gap-1">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="size-7"
                              onClick={() =>
                                feedback.mutate({
                                  target_type: "paper_match",
                                  target_id: match.id,
                                  value: "upvote",
                                })
                              }
                            >
                              <ThumbsUp className="size-3" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="size-7"
                              onClick={() =>
                                feedback.mutate({
                                  target_type: "paper_match",
                                  target_id: match.id,
                                  value: "downvote",
                                })
                              }
                            >
                              <ThumbsDown className="size-3" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="size-7"
                              onClick={() => handleNotInterested(match.id)}
                            >
                              <EyeOff className="size-3" />
                            </Button>
                          </div>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {match.rationale}
                        </p>
                        {match.paper_authors &&
                          match.paper_authors.length > 0 && (
                            <p className="text-xs text-muted-foreground">
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
    </AppShell>
  );
}
