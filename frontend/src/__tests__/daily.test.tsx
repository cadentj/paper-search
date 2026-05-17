import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DailyPage from "@/app/daily/page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/daily",
}));

const mockApi = vi.hoisted(() => ({
  getLatestSearchRun: vi.fn(),
  getSearchRun: vi.fn(),
  getSearchRunMatches: vi.fn(),
  createDailySearchRun: vi.fn(),
  submitFeedback: vi.fn(),
  getFilters: vi.fn(),
  createFilter: vi.fn(),
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

  it("shows empty state when no search run exists", async () => {
    mockApi.getLatestSearchRun.mockResolvedValue(null);
    renderWithProviders(<DailyPage />);
    await waitFor(() => {
      expect(screen.getByText(/no daily search has been run/i)).toBeInTheDocument();
    });
  });

  it("shows loading skeletons when search is running", async () => {
    mockApi.getLatestSearchRun.mockResolvedValue({ id: "r1", status: "running" });
    mockApi.getSearchRun.mockResolvedValue({ id: "r1", status: "running" });
    renderWithProviders(<DailyPage />);
    await waitFor(() => {
      expect(screen.getByText(/searching/i)).toBeInTheDocument();
    });
  });

  it("shows failed state", async () => {
    mockApi.getLatestSearchRun.mockResolvedValue({ id: "r1", status: "failed" });
    mockApi.getSearchRun.mockResolvedValue({
      id: "r1",
      status: "failed",
      error: "Something went wrong",
    });
    renderWithProviders(<DailyPage />);
    await waitFor(() => {
      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    });
  });

  it("shows completed state with summary and matches", async () => {
    mockApi.getLatestSearchRun.mockResolvedValue({ id: "r1", status: "completed" });
    mockApi.getSearchRun.mockResolvedValue({
      id: "r1",
      status: "completed",
      summary: "Today we found interesting papers on reasoning.",
      summary_citations: [{ arxivId: "2401.00001", citedFor: "reasoning evidence" }],
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
        filter_name: "LLM Reasoning",
      },
    ]);
    renderWithProviders(<DailyPage />);
    await waitFor(() => {
      expect(screen.getByText(/daily summary/i)).toBeInTheDocument();
      expect(screen.getByText(/today we found interesting papers/i)).toBeInTheDocument();
      expect(screen.getByText("CoT Paper")).toBeInTheDocument();
    });
  });
});
