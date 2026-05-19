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
  getSearchRunSummary: vi.fn(),
  getDailySearchJob: vi.fn(),
  createDailySearchRun: vi.fn(),
  createDailySearchSummary: vi.fn(),
  getDailySearchSummaryJob: vi.fn(),
  getDailyCandidateCount: vi.fn(),
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
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.getDailyCandidateCount.mockResolvedValue({
      date: "2026-05-18",
      count: 5,
      counts_by_source: { arxiv: 5 },
    });
  });

  it("shows loading skeletons when search is running", async () => {
    mockApi.getLatestSearchRun.mockResolvedValue({
      id: "r1",
      job_id: "j1",
      status: "running",
    });
    mockApi.getSearchRun.mockResolvedValue({
      id: "r1",
      status: "running",
    });
    mockApi.getDailySearchJob.mockResolvedValue({
      job: {
        id: "j1",
        kind: "daily_search",
        status: "running",
        subject_type: "search_run",
        subject_id: "r1",
        progress: {
          stage: "matching_filters",
          current: 2,
          total: 5,
          message: "Matching filter 1/3: LLM Reasoning",
          log: [
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
        },
        created_at: "2026-05-17T19:00:00Z",
        updated_at: "2026-05-17T19:00:01Z",
      },
      subject: { id: "r1", job_id: "j1", status: "running" },
      items: [
        {
          id: "m1",
          search_run_id: "r1",
          filter_id: "f1",
          paper_id: "p1",
          result: "Already found during the run",
          created_at: "2026-05-17T19:00:00Z",
          paper_title: "Streaming Match",
          paper_authors: ["Author A"],
          filter_name: "LLM Reasoning",
        },
      ],
      next_cursor: "cursor-1",
      done: false,
    });
    renderWithProviders(<DailyPage />);
    await waitFor(() => {
      expect(screen.getByText(/searching/i)).toBeInTheDocument();
      expect(screen.getAllByText(/matching filter 1\/3/i).length).toBeGreaterThan(0);
      expect(screen.getByText("40%")).toBeInTheDocument();
      expect(mockApi.getSearchRunMatches).not.toHaveBeenCalled();
      expect(screen.getByRole("button", { name: /LLM Reasoning/i })).toBeInTheDocument();
    });
  });

  it("shows completed state with summary and collapsed matches", async () => {
    mockApi.getLatestSearchRun.mockResolvedValue({ id: "r1", status: "completed" });
    mockApi.getSearchRun.mockResolvedValue({
      id: "r1",
      status: "completed",
      match_count: 1,
      candidate_count: 5,
    });
    mockApi.getSearchRunSummary.mockResolvedValue({
      search_run_id: "r1",
      summary:
        'Today we found interesting papers on reasoning <cite arxivId="2401.00001"/>.',
      citations: [
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
        result:
          "Directly addresses reasoning; emphasizes chain-of-thought improvements.",
        created_at: "2026-05-17T19:00:00Z",
        paper_title: "CoT Paper",
        paper_authors: ["Author A"],
        paper_source_type: "arxiv",
        paper_source_id: "2401.00001",
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
