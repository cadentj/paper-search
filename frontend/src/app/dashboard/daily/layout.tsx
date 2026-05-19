"use client";

import { DailyChrome } from "@/components/daily/daily-chrome";
import { DailyProvider } from "@/components/daily/daily-provider";
import type { ReactNode } from "react";

export default function DailyLayout({ children }: { children: ReactNode }) {
  return (
    <DailyProvider>
      <DailyChrome>{children}</DailyChrome>
    </DailyProvider>
  );
}
