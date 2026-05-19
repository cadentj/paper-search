"use client";

import { Card, CardContent } from "@/components/ui/card";
import { useDaily } from "@/components/daily/daily-provider";
import {
  DailySummary,
  MatchesSection,
  SearchProgress,
} from "@/components/daily/daily-ui";

export function DailyReportView() {
  const {
    isJobRunning,
    isSummaryRunning,
    createSearchPending,
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
    isRunning,
  } = useDaily();

  return (
    <div className="space-y-6">
      {(isJobRunning || isSummaryRunning || createSearchPending) && (
        <SearchProgress
          job={isSummaryRunning ? summaryJob : activeJob}
          progressPercent={progressPercent}
          matchCount={matches.length}
          isCreating={createSearchPending}
          isSummarizing={isSummaryRunning}
        />
      )}
      {summary && <DailySummary summary={summary} matches={matches} />}
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
              No matches found. Try running a daily search or adding more filters.
            </p>
          </CardContent>
        </Card>
      )}
      {!run && !isRunning && (
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-muted-foreground">
              No daily search has been run yet. Click &quot;Run Daily Search&quot; to get
              started.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
