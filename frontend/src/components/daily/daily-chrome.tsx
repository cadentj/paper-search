"use client";

import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  DAILY_SEARCH_DATE_SET,
  DAILY_SEARCH_END,
  DAILY_SEARCH_START,
  useDaily,
} from "@/components/daily/daily-provider";
import { DailyHeader } from "@/components/daily/daily-ui";

function isDailyReportPath(pathname: string) {
  return (
    pathname === "/dashboard/daily" ||
    pathname === "/dashboard/daily/report" ||
    pathname.startsWith("/dashboard/daily/report/")
  );
}

export function DailyChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const showRunSearch = isDailyReportPath(pathname);
  const isAllPapers = pathname.startsWith("/dashboard/daily/all-papers");
  const {
    effectiveSelectedDate,
    selectedDateCount,
    selectedDateBreakdown,
    hasSelectedDate,
    handleDateChange,
    isRunning,
    isCreating,
    handleRunSearch,
    selectedPaperId,
  } = useDaily();

  return (
    <div
      className={cn(
        "flex-1 space-y-6 p-6",
        isAllPapers && selectedPaperId ? "max-w-7xl" : "max-w-5xl"
      )}
    >
      <DailyHeader
        selectedDate={effectiveSelectedDate}
        dateStatus={{
          hasSelectedDate,
          count: selectedDateCount,
          breakdown: selectedDateBreakdown,
        }}
        minDate={DAILY_SEARCH_START}
        maxDate={DAILY_SEARCH_END}
        availableDateSet={DAILY_SEARCH_DATE_SET}
        onDateChange={handleDateChange}
        runAction={
          showRunSearch
            ? {
                isRunning,
                isCreating,
                onRunSearch: handleRunSearch,
              }
            : undefined
        }
      />
      {children}
    </div>
  );
}
