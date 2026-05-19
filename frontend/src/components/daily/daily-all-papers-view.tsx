"use client";

import { useDaily } from "@/components/daily/daily-provider";
import { DailyAllPapersContent } from "@/components/daily/daily-ui";

export function DailyAllPapersView() {
  const {
    effectiveSelectedDate,
    selectedPaperId,
    setSelectedPaperId,
  } = useDaily();

  return (
    <DailyAllPapersContent
      key={effectiveSelectedDate}
      selectedDate={effectiveSelectedDate}
      selectedPaperId={selectedPaperId}
      onSelectPaper={setSelectedPaperId}
      onClosePreview={() => setSelectedPaperId(null)}
    />
  );
}
