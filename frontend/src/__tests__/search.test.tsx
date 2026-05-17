import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SearchPage from "@/app/search/page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/search",
}));

const mockApi = vi.hoisted(() => ({
  getSearchRuns: vi.fn(),
  getSearchRun: vi.fn(),
  getSearchRunMatches: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: mockApi,
}));

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("SearchPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows empty state when no runs", async () => {
    mockApi.getSearchRuns.mockResolvedValue([]);
    renderWithProviders(<SearchPage />);
    await waitFor(() => {
      expect(screen.getByText(/no search runs yet/i)).toBeInTheDocument();
    });
  });

  it("lists previous daily runs", async () => {
    mockApi.getSearchRuns.mockResolvedValue([
      {
        id: "r1",
        status: "completed",
        run_date: "2024-01-15",
        match_count: 3,
        created_at: "2024-01-15T10:00:00Z",
      },
      {
        id: "r2",
        status: "failed",
        run_date: "2024-01-14",
        match_count: 0,
        created_at: "2024-01-14T10:00:00Z",
      },
    ]);
    renderWithProviders(<SearchPage />);
    await waitFor(() => {
      expect(screen.getByText("2024-01-15")).toBeInTheDocument();
      expect(screen.getByText("2024-01-14")).toBeInTheDocument();
      expect(screen.getByText("3 matches")).toBeInTheDocument();
    });
  });
});
