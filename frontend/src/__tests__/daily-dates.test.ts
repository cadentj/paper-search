import { describe, expect, it } from "vitest";
import {
  DAILY_SEARCH_DATES,
  DAILY_SEARCH_END,
  DAILY_SEARCH_START,
  DEFAULT_DAILY_SEARCH_DATE,
  isDailySearchDate,
} from "@/lib/daily-dates";

describe("daily-dates", () => {
  it("enumerates the configured window", () => {
    expect(DAILY_SEARCH_DATES[0]).toBe(DAILY_SEARCH_START);
    expect(DAILY_SEARCH_DATES[DAILY_SEARCH_DATES.length - 1]).toBe(DAILY_SEARCH_END);
    expect(DAILY_SEARCH_DATES).toHaveLength(31);
    expect(DEFAULT_DAILY_SEARCH_DATE).toBe(DAILY_SEARCH_END);
  });

  it("validates membership", () => {
    expect(isDailySearchDate(DAILY_SEARCH_START)).toBe(true);
    expect(isDailySearchDate("2020-01-01")).toBe(false);
  });
});
