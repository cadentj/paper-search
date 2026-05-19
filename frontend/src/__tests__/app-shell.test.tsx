import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "@/components/app-shell";

const mockPathname = vi.hoisted(() => ({ current: "/dashboard/filters" }));

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname.current,
}));

const mockApi = vi.hoisted(() => ({
  getFeedbackStatus: vi.fn(),
  getJobsOverview: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: mockApi,
}));

describe("AppShell navigation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPathname.current = "/dashboard/filters";
    mockApi.getFeedbackStatus.mockResolvedValue({
      pending_votes: 0,
      pending_notes: 0,
      pending_proposals: 0,
    });
    mockApi.getJobsOverview.mockResolvedValue({ active: [], recent: [] });
  });

  it("shows Filters, Daily with nested Report and All Papers, and Settings", () => {
    mockPathname.current = "/dashboard/daily/report";
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <AppShell>
          <div>Content</div>
        </AppShell>
      </QueryClientProvider>
    );

    const links = screen.getAllByRole("link");
    const navHrefs = links.map((link) => link.getAttribute("href"));

    expect(navHrefs).toContain("/dashboard/filters");
    expect(navHrefs).toContain("/dashboard/daily/report");
    expect(navHrefs).toContain("/dashboard/daily/all-papers");
    expect(navHrefs).toContain("/dashboard/settings");
    expect(navHrefs).toContain("/dashboard/jobs");
    expect(navHrefs).not.toContain("/dashboard/search");

    expect(screen.getByText("Filters")).toBeInTheDocument();
    expect(screen.getByText("Daily")).toBeInTheDocument();
    expect(screen.getByText("Report")).toBeInTheDocument();
    expect(screen.getByText("All Papers")).toBeInTheDocument();
    expect(screen.getByText("Jobs")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
    expect(screen.queryByText("Search")).not.toBeInTheDocument();
  });

  it("shows report activity indicator when a report job is active", async () => {
    mockPathname.current = "/dashboard/daily/report";
    mockApi.getJobsOverview.mockResolvedValue({
      active: [
        {
          job: {
            id: "job-1",
            kind: "daily_search",
            status: "running",
            queue_name: "reports",
            progress: { current: 1, total: 10 },
            created_at: new Date().toISOString(),
          },
          label: "Daily search",
          detail: "2026-05-19",
          href: "/dashboard/daily/report",
        },
      ],
      recent: [],
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <AppShell>
          <div>Content</div>
        </AppShell>
      </QueryClientProvider>
    );

    await screen.findByText("Report");
    await waitFor(() => {
      expect(document.querySelector(".animate-spin")).not.toBeNull();
    });
  });
});
