"use client";

import { useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { SummaryText } from "@/components/summary-text";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useSearchRuns,
  useSearchRunMatches,
  useSearchRun,
  useSearchRunSummary,
} from "@/hooks/use-queries";
import { ChevronDown, ChevronRight, Calendar, FileText } from "lucide-react";

const TIME_FORMATTER = new Intl.DateTimeFormat(undefined, {
  hour: "numeric",
  minute: "2-digit",
});
const SEARCH_SKELETON_KEYS = [
  "search-skeleton-1",
  "search-skeleton-2",
  "search-skeleton-3",
];

function RunCreatedTime({ value }: { value: string }) {
  return (
    <span suppressHydrationWarning>
      {TIME_FORMATTER.format(new Date(value))}
    </span>
  );
}

export default function SearchPage() {
  const { data: runs, isLoading } = useSearchRuns();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const { data: selectedRun } = useSearchRun(selectedRunId);
  const { data: selectedSummary } = useSearchRunSummary(
    selectedRunId,
    selectedRun?.status === "completed"
  );
  const { data: matches } = useSearchRunMatches(
    selectedRun?.status === "completed" ? selectedRunId : null
  );

  const statusColor = (status: string) => {
    switch (status) {
      case "completed":
        return "bg-green-100 text-green-800";
      case "failed":
        return "bg-red-100 text-red-800";
      case "running":
        return "bg-blue-100 text-blue-800";
      default:
        return "bg-gray-100 text-gray-800";
    }
  };

  return (
    <div className="flex-1 p-6 space-y-6 max-w-4xl">
        <h1 className="text-2xl font-semibold tracking-tight">Search History</h1>

        {isLoading && (
          <div className="space-y-3">
            {SEARCH_SKELETON_KEYS.map((key) => (
              <Skeleton key={key} className="h-16 w-full" />
            ))}
          </div>
        )}

        {runs && runs.length === 0 && (
          <Card>
            <CardContent className="pt-6 text-center">
              <p className="text-muted-foreground">
                No search runs yet. Go to the Daily page to run your first
                search.
              </p>
            </CardContent>
          </Card>
        )}

        <div className="space-y-3">
          {runs?.map((run) => (
            <Card key={run.id}>
              <CardHeader className="pb-2">
                <button
                  type="button"
                  className="flex w-full items-center justify-between text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-expanded={selectedRunId === run.id}
                  onClick={() =>
                    setSelectedRunId(
                      selectedRunId === run.id ? null : run.id
                    )
                  }
                >
                  <div className="flex items-center gap-3">
                    {selectedRunId === run.id ? (
                      <ChevronDown className="size-4" />
                    ) : (
                      <ChevronRight className="size-4" />
                    )}
                    <div>
                      <CardTitle className="text-sm">
                        <Calendar className="inline mr-1 size-3" />
                        {run.run_date}
                      </CardTitle>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        <RunCreatedTime value={run.created_at} />
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge
                      variant="secondary"
                      className={statusColor(run.status)}
                    >
                      {run.status}
                    </Badge>
                    {run.match_count != null && (
                      <Badge variant="outline">
                        <FileText className="mr-1 size-3" />
                        {run.match_count} matches
                      </Badge>
                    )}
                  </div>
                </button>
              </CardHeader>

              {selectedRunId === run.id && selectedRun && (
                <CardContent className="space-y-3">
                  {selectedSummary && (
                    <div className="rounded-lg bg-muted/50 p-3">
                      <p className="text-xs font-medium text-muted-foreground mb-1">
                        Summary
                      </p>
                      <SummaryText
                        summary={selectedSummary.summary}
                        citations={selectedSummary.citations}
                        matches={matches || []}
                        className="whitespace-pre-wrap text-sm"
                      />
                    </div>
                  )}

                  {matches && matches.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs font-medium text-muted-foreground">
                        Matches
                      </p>
                      {matches.map((m) => (
                        <div
                          key={m.id}
                          className="rounded border p-2 text-sm space-y-1"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-medium">
                              {m.paper_title}
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {m.result}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}

                  {selectedRun.error && (
                    <p className="text-sm text-destructive">
                      {selectedRun.error}
                    </p>
                  )}
                </CardContent>
              )}
            </Card>
          ))}
        </div>
    </div>
  );
}
