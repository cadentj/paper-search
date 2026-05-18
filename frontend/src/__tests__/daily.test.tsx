import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DailyPage from "@/app/dashboard/daily/page";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard/daily",
}));

const mockApi = vi.hoisted(() => ({
  getLatestSearchRun: vi.fn(),
  getSearchRun: vi.fn(),
  getSearchRunMatches: vi.fn(),
  createDailySearchRun: vi.fn(),
  getFilters: vi.fn(),
  createFilter: vi.fn(),
  archiveFilter: vi.fn(),
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

describe("DailyPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows loading skeletons when search is running", async () => {
    mockApi.getLatestSearchRun.mockResolvedValue({ id: "r1", status: "running" });
    mockApi.getSearchRun.mockResolvedValue({
      id: "r1",
      status: "running",
      stage: "matching_filters",
      progress_current: 2,
      progress_total: 5,
      progress_message: "Matching filter 1/3: LLM Reasoning",
      progress_log: [
        {
          at: "2026-05-17T19:00:00Z",
          stage: "fetching_papers",
          message: "Fetched 50 arXiv papers",
        },
        {
          at: "2026-05-17T19:00:01Z",
          stage: "matching_filters",
          message: "Matching filter 1/3: LLM Reasoning",
        },
      ],
    });
    mockApi.getSearchRunMatches.mockResolvedValue([
      {
        id: "m1",
        filter_id: "f1",
        paper_id: "p1",
        stance: "supports",
        relevance_score: 0.85,
        rationale: "Already found during the run",
        matched_claims: [],
        abstract_evidence: [],
        paper_title: "Streaming Match",
        paper_authors: ["Author A"],
        filter_name: "LLM Reasoning",
      },
    ]);
    renderWithProviders(<DailyPage />);
    await waitFor(() => {
      expect(screen.getByText(/searching/i)).toBeInTheDocument();
      expect(screen.getAllByText(/matching filter 1\/3/i).length).toBeGreaterThan(0);
      expect(screen.getByText("40%")).toBeInTheDocument();
      expect(mockApi.getSearchRunMatches).toHaveBeenCalled();
      expect(screen.getByRole("button", { name: /LLM Reasoning/i })).toBeInTheDocument();
    });
  });

  it("shows completed state with summary and collapsed matches", async () => {
    mockApi.getLatestSearchRun.mockResolvedValue({ id: "r1", status: "completed" });
    mockApi.getSearchRun.mockResolvedValue({
      id: "r1",
      status: "completed",
      summary:
        'Today we found interesting papers on reasoning <cite arxivId="2401.00001"/>.',
      summary_citations: [
        {
          arxivId: "2401.00001",
          paperMatchId: "m1",
          citedFor: "reasoning evidence",
        },
      ],
      match_count: 1,
      candidate_count: 5,
    });
    mockApi.getSearchRunMatches.mockResolvedValue([
      {
        id: "m1",
        filter_id: "f1",
        paper_id: "p1",
        stance: "supports",
        relevance_score: 0.85,
        rationale: "Directly addresses reasoning",
        matched_claims: ["Chain-of-thought"],
        abstract_evidence: [],
        paper_title: "CoT Paper",
        paper_authors: ["Author A"],
        paper_arxiv_id: "2401.00001",
        filter_name: "LLM Reasoning",
      },
    ]);
    renderWithProviders(<DailyPage />);
    await waitFor(() => {
      expect(screen.getByText(/daily summary/i)).toBeInTheDocument();
      expect(screen.getByText(/today we found interesting papers/i)).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: /open citation 1: 2401.00001/i })
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /LLM Reasoning/i })).toBeInTheDocument();
    });

    expect(
      screen.getByRole("link", { name: /open citation 1: 2401.00001/i })
    ).toHaveAttribute("href", "/dashboard/papers/p1");
    expect(screen.queryByText(/reasoning evidence/i)).not.toBeInTheDocument();

    expect(screen.queryByText("CoT Paper")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /LLM Reasoning/i }));
    expect(await screen.findByText("CoT Paper")).toBeInTheDocument();
    expect(screen.queryByLabelText(/mark paper match/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/hide paper match/i)).not.toBeInTheDocument();
  });
});
