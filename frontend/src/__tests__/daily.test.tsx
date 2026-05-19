import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DailyProvider } from "@/components/daily/daily-provider";
import { DailyChrome } from "@/components/daily/daily-chrome";
import { DailyReportView } from "@/components/daily/daily-report-view";
import { DailyAllPapersView } from "@/components/daily/daily-all-papers-view";

const mockPathname = vi.hoisted(() => ({ current: "/dashboard/daily/report" }));

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname.current,
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
  archiveFilter: vi.fn(),
  getDailyPapers: vi.fn(),
  getPaper: vi.fn(),
  getPaperHtml: vi.fn(),
  submitPaperFeedback: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: mockApi,
}));

function renderDaily(
  ui: React.ReactElement,
  pathname = "/dashboard/daily/report"
) {
  mockPathname.current = pathname;
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <DailyProvider>
        <DailyChrome>{ui}</DailyChrome>
      </DailyProvider>
    </QueryClientProvider>
  );
}

describe("Daily report page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPathname.current = "/dashboard/daily/report";
    mockApi.getDailyCandidateCount.mockResolvedValue({
      date: "2026-05-18",
      count: 5,
      counts_by_source: { arxiv: 5 },
    });
    mockApi.getDailyPapers.mockResolvedValue({
      papers: [
        {
          id: "p1",
          title: "Daily Paper One",
          authors: ["Author A"],
          source_type: "arxiv",
          source_id: "2401.00001",
          search_text: "Abstract text",
          created_at: "2026-05-17T19:00:00Z",
        },
      ],
      total: 1,
      page: 1,
      per_page: 20,
    });
    mockApi.getPaper.mockResolvedValue({
      id: "p1",
      title: "Daily Paper One",
      authors: ["Author A"],
      source_type: "arxiv",
      source_id: "2401.00001",
      search_text: "Full paper text for preview",
      created_at: "2026-05-17T19:00:00Z",
    });
    mockApi.getPaperHtml.mockResolvedValue({ html: null, source_url: null });
    mockApi.submitPaperFeedback.mockResolvedValue({});
  });

  it("does not show quick-add filter UI", async () => {
    mockApi.getLatestSearchRun.mockResolvedValue(null);
    renderDaily(<DailyReportView />);
    await waitFor(() => {
      expect(screen.getByText("Daily")).toBeInTheDocument();
    });
    expect(screen.queryByLabelText(/quick add filter/i)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/quick add a filter/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run daily search/i })).toBeInTheDocument();
  });

  it("shows loading state when search is running", async () => {
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
          log: [],
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
    renderDaily(<DailyReportView />);
    await waitFor(() => {
      expect(screen.getByText(/searching/i)).toBeInTheDocument();
      expect(screen.getByText("40%")).toBeInTheDocument();
      expect(screen.getByText(/2 \/ 5 evaluations/i)).toBeInTheDocument();
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
        filter_mode: "claim",
      },
    ]);
    renderDaily(<DailyReportView />);
    await waitFor(() => {
      expect(screen.getByText(/daily summary/i)).toBeInTheDocument();
      expect(screen.getByText(/today we found interesting papers/i)).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: /open citation 1: 2401.00001/i })
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /LLM Reasoning/i })).toBeInTheDocument();
      expect(screen.getByText("Claim")).toBeInTheDocument();
    });

    expect(
      screen.getByRole("link", { name: /open citation 1: 2401.00001/i })
    ).toHaveAttribute("href", "/dashboard/papers/p1");
    expect(screen.queryByText(/reasoning evidence/i)).not.toBeInTheDocument();
    expect(screen.queryByText("CoT Paper")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /LLM Reasoning/i }));
    expect(await screen.findByText("CoT Paper")).toBeInTheDocument();
  });
});

describe("Daily all papers page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.getDailyCandidateCount.mockResolvedValue({
      date: "2026-05-18",
      count: 5,
      counts_by_source: { arxiv: 5 },
    });
    mockApi.getDailyPapers.mockResolvedValue({
      papers: [
        {
          id: "p1",
          title: "Daily Paper One",
          authors: ["Author A"],
          source_type: "arxiv",
          source_id: "2401.00001",
          search_text: "Abstract text",
          created_at: "2026-05-17T19:00:00Z",
        },
      ],
      total: 1,
      page: 1,
      per_page: 20,
    });
    mockApi.getPaper.mockResolvedValue({
      id: "p1",
      title: "Daily Paper One",
      authors: ["Author A"],
      source_type: "arxiv",
      source_id: "2401.00001",
      search_text: "Full paper text for preview",
      created_at: "2026-05-17T19:00:00Z",
    });
    mockApi.getPaperHtml.mockResolvedValue({ html: null, source_url: null });
    mockApi.submitPaperFeedback.mockResolvedValue({});
    mockApi.getLatestSearchRun.mockResolvedValue(null);
  });

  it("shows paper list without collapsible and opens preview on click", async () => {
    renderDaily(<DailyAllPapersView />, "/dashboard/daily/all-papers");

    await waitFor(() => {
      expect(mockApi.getDailyPapers).toHaveBeenCalled();
      expect(screen.getByText("Daily Paper One")).toBeInTheDocument();
    });
    expect(screen.queryByText(/all papers for/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run daily search/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /daily paper one/i }));

    await waitFor(() => {
      expect(mockApi.getPaper).toHaveBeenCalledWith("p1");
      expect(screen.getByText("Full paper text for preview")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /close preview/i }));
    expect(screen.queryByText("Full paper text for preview")).not.toBeInTheDocument();
  });
});
