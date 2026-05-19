"use client";

import { Card, CardContent } from "@/components/ui/card";
import { useDaily } from "@/components/daily/daily-provider";
import {
  DailyPaperSplitLayout,
  DailySummary,
  MatchesSection,
  SearchProgress,
} from "@/components/daily/daily-ui";
import { PaperReadPreview } from "@/components/paper-read-preview";

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
    selectedPaperId,
    setSelectedPaperId,
  } = useDaily();

  const hasPartialSummary = Boolean(summary?.summary?.trim());
  const summaryJobFinished =
    summaryJob &&
    !isSummaryRunning &&
    (summaryJob.status === "completed" || summaryJob.status === "failed");
  const showSummaryMissing = Boolean(summaryJobFinished && !hasPartialSummary);
  const showSummaryProgress = isSummaryRunning && !hasPartialSummary;
  const showSearchProgress =
    isJobRunning || createSearchPending || showSummaryProgress;
  const isSummaryStreaming = isSummaryRunning && hasPartialSummary;

  const handleSelectPaper = (paperId: string) => {
    setSelectedPaperId(paperId);
  };

  const reportContent = (
    <div className="space-y-6">
      {showSearchProgress && (
        <SearchProgress
          job={showSummaryProgress ? summaryJob : activeJob}
          progressPercent={progressPercent}
          matchCount={matches.length}
          isCreating={createSearchPending}
          isSummarizing={showSummaryProgress}
        />
      )}
      {hasPartialSummary && summary && (
        <DailySummary
          summary={summary}
          matches={matches}
          isStreaming={isSummaryStreaming}
          onSelectPaper={handleSelectPaper}
        />
      )}
      {showSummaryMissing && (
        <Card className="border-destructive">
          <CardContent className="pt-4">
            <p className="text-sm text-destructive">
              {summaryJob?.status === "failed" && summaryJob.error
                ? summaryJob.error
                : "Daily summary finished but no summary text was saved. Run daily search again to regenerate it."}
            </p>
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
      <MatchesSection
        matchesByFilter={matchesByFilter}
        expandedFilters={expandedFilters}
        isArchiving={archiveFilter.isPending}
        onToggleFilter={toggleFilter}
        onArchiveFilter={(filterId) => archiveFilter.mutate(filterId)}
        selectedPaperId={selectedPaperId}
        onSelectPaper={handleSelectPaper}
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

  if (selectedPaperId) {
    return (
      <DailyPaperSplitLayout
        summary={reportContent}
        preview={
          <PaperReadPreview
            paperId={selectedPaperId}
            onClose={() => setSelectedPaperId(null)}
          />
        }
      />
    );
  }

  return (
    <div className="flex min-h-0 w-full flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto p-1">{reportContent}</div>
    </div>
  );
}
