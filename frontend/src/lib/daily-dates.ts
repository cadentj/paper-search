import { addDays, format, parseISO } from "date-fns";

// Keep in sync with backend/app/services/daily_dates.py
export const DAILY_SEARCH_START = "2026-04-14";
export const DAILY_SEARCH_END = "2026-05-14";
export const DEFAULT_DAILY_SEARCH_DATE = DAILY_SEARCH_END;

function enumerateDailySearchDates(start: string, end: string): string[] {
  const dates: string[] = [];
  let current = parseISO(`${start}T00:00:00`);
  const last = parseISO(`${end}T00:00:00`);
  while (current <= last) {
    dates.push(format(current, "yyyy-MM-dd"));
    current = addDays(current, 1);
  }
  return dates;
}

export const DAILY_SEARCH_DATES = enumerateDailySearchDates(
  DAILY_SEARCH_START,
  DAILY_SEARCH_END
);

export const DAILY_SEARCH_DATE_SET = new Set(DAILY_SEARCH_DATES);

export function isDailySearchDate(value: string): boolean {
  return DAILY_SEARCH_DATE_SET.has(value);
}
