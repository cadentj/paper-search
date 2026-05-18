import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SearchPage from "@/app/dashboard/search/page";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard/search",
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

  it("renders selected run summary citations inline", async () => {
    mockApi.getSearchRuns.mockResolvedValue([
      {
        id: "r1",
        status: "completed",
        run_date: "2024-01-15",
        match_count: 1,
        created_at: "2024-01-15T10:00:00Z",
      },
    ]);
    mockApi.getSearchRun.mockResolvedValue({
      id: "r1",
      status: "completed",
      summary: 'Reasoning work stood out <cite arxivId="2401.00001"/>.',
      summary_citations: [
        {
          arxivId: "2401.00001",
          paperMatchId: "m1",
          citedFor: "reasoning evidence",
        },
      ],
    });
    mockApi.getSearchRunMatches.mockResolvedValue([
      {
        id: "m1",
        search_run_id: "r1",
        filter_id: "f1",
        paper_id: "p1",
        result: "Directly addresses reasoning.",
        created_at: "2026-05-17T19:00:00Z",
        paper_title: "CoT Paper",
        paper_arxiv_id: "2401.00001",
        filter_name: "LLM Reasoning",
      },
    ]);

    renderWithProviders(<SearchPage />);
    fireEvent.click(await screen.findByRole("button", { name: /2024-01-15/i }));

    const citation = await screen.findByRole("link", {
      name: /open citation 1: 2401.00001/i,
    });
    expect(screen.getByText(/reasoning work stood out/i)).toBeInTheDocument();
    expect(screen.queryByText(/2401.00001: reasoning evidence/i)).not.toBeInTheDocument();
    expect(citation).toHaveAttribute("href", "/dashboard/papers/p1");
  });
});
