import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import FiltersPage from "@/app/dashboard/filters/page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/dashboard/filters",
}));

const mockApi = vi.hoisted(() => ({
  getFilters: vi.fn(),
  createFilter: vi.fn(),
  archiveFilter: vi.fn(),
  restoreFilter: vi.fn(),
  updateFilter: vi.fn(),
  getJob: vi.fn(),
  uploadDocument: vi.fn(),
  getDocument: vi.fn(),
  createOnboardingGeneration: vi.fn(),
  promoteDraftFilters: vi.fn(),
  getFeedbackStatus: vi.fn(),
  verifyScholarProfile: vi.fn(),
  startScholarImport: vi.fn(),
  getScholarImportStatus: vi.fn(),
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

describe("FiltersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.getFeedbackStatus.mockResolvedValue({
      pending_votes: 0,
      pending_notes: 0,
      pending_proposals: 0,
    });
  });

  it("shows active and archived filters", async () => {
    mockApi.getFilters.mockImplementation((status?: string) => {
      if (status === "draft") return Promise.resolve([]);
      return Promise.resolve([
        {
          id: "f1",
          name: "Active Filter",
          status: "active",
          definition: {
            name: "Active Filter",
            description: "Test statement",
            mode: "claim",
          },
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        {
          id: "f2",
          name: "Archived Filter",
          status: "archived",
          definition: {
            name: "Archived Filter",
            description: "Old statement",
            mode: "topic",
          },
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
          archived_at: "2024-01-02T00:00:00Z",
        },
      ]);
    });
    renderWithProviders(<FiltersPage />);
    await waitFor(() => {
      expect(screen.getByText("Active Filter")).toBeInTheDocument();
      expect(screen.getByText(/active \(1\)/i)).toBeInTheDocument();
      expect(screen.getByText("Claim")).toBeInTheDocument();
    });

    const archivedToggle = screen.getByRole("button", {
      name: /archived \(1\)/i,
    });
    expect(archivedToggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Archived Filter")).not.toBeInTheDocument();

    fireEvent.click(archivedToggle);

    expect(archivedToggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Archived Filter")).toBeInTheDocument();
    expect(screen.getByText("Topic")).toBeInTheDocument();
  });

  it("shows research context input for generating filters", async () => {
    mockApi.getFilters.mockImplementation(() => Promise.resolve([]));
    renderWithProviders(<FiltersPage />);
    await waitFor(() => {
      expect(screen.getByText("Research context")).toBeInTheDocument();
      expect(
        screen.getByPlaceholderText(
          /add a research direction/i
        )
      ).toBeInTheDocument();
    });
  });

  it("shows empty state when no filters exist", async () => {
    mockApi.getFilters.mockImplementation(() => Promise.resolve([]));
    renderWithProviders(<FiltersPage />);
    await waitFor(() => {
      expect(
        screen.getByText(/no filters yet/i)
      ).toBeInTheDocument();
    });
  });

  it("hides Semantic Scholar import card when scholar filters exist", async () => {
    mockApi.getFilters.mockImplementation((status?: string) => {
      if (status === "draft") return Promise.resolve([]);
      return Promise.resolve([
        {
          id: "f1",
          name: "Scholar Filter",
          status: "active",
          source: "scholar",
          definition: {
            name: "Scholar Filter",
            description: "From profile",
            mode: "topic",
          },
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
      ]);
    });
    renderWithProviders(<FiltersPage />);
    await waitFor(() => {
      expect(screen.getByText("Scholar Filter")).toBeInTheDocument();
    });
    expect(
      screen.queryByText("Semantic Scholar Profile Import")
    ).not.toBeInTheDocument();
  });

  it("hides Semantic Scholar import card after successful import", async () => {
    mockApi.getFilters.mockImplementation(() => Promise.resolve([]));
    mockApi.verifyScholarProfile.mockResolvedValue({
      author_id: "a1",
      name: "Test Author",
      affiliations: [],
      paper_count: 10,
    });
    mockApi.startScholarImport.mockResolvedValue({ id: "imp1", job_id: "j1" });
    mockApi.getScholarImportStatus.mockResolvedValue({ status: "completed" });

    renderWithProviders(<FiltersPage />);
    expect(
      await screen.findByText("Semantic Scholar Profile Import")
    ).toBeInTheDocument();

    fireEvent.change(
      screen.getByPlaceholderText(/paste semantic scholar profile url/i),
      { target: { value: "https://www.semanticscholar.org/author/123" } }
    );
    fireEvent.click(screen.getByRole("button", { name: /verify/i }));
    expect(await screen.findByText(/test author/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /import & generate filters/i }));

    await waitFor(
      () => {
        expect(
          screen.queryByText("Semantic Scholar Profile Import")
        ).not.toBeInTheDocument();
      },
      { timeout: 5000 }
    );
  });
});
