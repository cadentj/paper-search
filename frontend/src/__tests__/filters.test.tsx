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
  beforeEach(() => vi.clearAllMocks());

  it("shows empty state when no filters", async () => {
    mockApi.getFilters.mockResolvedValue([]);
    renderWithProviders(<FiltersPage />);
    await waitFor(() => {
      expect(screen.getByText(/no filters yet/i)).toBeInTheDocument();
    });
  });

  it("shows active and archived filters", async () => {
    mockApi.getFilters.mockResolvedValue([
      {
        id: "f1",
        name: "Active Filter",
        status: "active",
        definition: {
          name: "Active Filter",
          description: "Test statement",
          mode: "warrants",
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
          mode: "relevance",
        },
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
        archived_at: "2024-01-02T00:00:00Z",
      },
    ]);
    renderWithProviders(<FiltersPage />);
    await waitFor(() => {
      expect(screen.getByText("Active Filter")).toBeInTheDocument();
      expect(screen.getByText(/active \(1\)/i)).toBeInTheDocument();
    });

    const archivedToggle = screen.getByRole("button", {
      name: /archived \(1\)/i,
    });
    expect(archivedToggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Archived Filter")).not.toBeInTheDocument();

    fireEvent.click(archivedToggle);

    expect(archivedToggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Archived Filter")).toBeInTheDocument();
  });
});
