import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import JobsPage from "@/app/dashboard/jobs/page";

const mockApi = vi.hoisted(() => ({
  getJobsOverview: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: mockApi,
}));

describe("Jobs page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders active and recent jobs with progress", async () => {
    mockApi.getJobsOverview.mockResolvedValue({
      active: [
        {
          job: {
            id: "active-1",
            kind: "daily_search",
            status: "running",
            queue_name: "reports",
            progress: { current: 3, total: 10 },
            created_at: "2026-05-19T12:00:00Z",
          },
          label: "Daily search",
          detail: "2026-05-19",
          href: "/dashboard/daily/report",
        },
      ],
      recent: [
        {
          job: {
            id: "recent-1",
            kind: "idea_map",
            status: "completed",
            queue_name: "idea_maps",
            progress: { current: 5, total: 5 },
            created_at: "2026-05-19T11:00:00Z",
            completed_at: "2026-05-19T11:05:00Z",
          },
          label: "Idea map",
          detail: "Test paper",
          href: "/dashboard/papers/paper-1",
        },
      ],
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <JobsPage />
      </QueryClientProvider>
    );

    expect(await screen.findByText("Daily search")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Recent")).toBeInTheDocument();
    expect(screen.getByText("running")).toBeInTheDocument();
    expect(screen.getByText("30%")).toBeInTheDocument();
    expect(screen.getByText("Idea map")).toBeInTheDocument();
    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByText("Queue: reports")).toBeInTheDocument();
  });
});
