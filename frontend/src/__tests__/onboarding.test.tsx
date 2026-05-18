import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import OnboardingPage from "@/app/onboarding/page";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), replace: vi.fn() }),
}));

// Mock the API module
const mockApi = vi.hoisted(() => ({
  getOnboardingStatus: vi.fn(),
  createOnboardingExtraction: vi.fn(),
  getOnboardingExtraction: vi.fn(),
  completeOnboarding: vi.fn(),
  resetOnboardingDev: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: mockApi,
  FilterDefinition: {},
}));

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe("OnboardingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.getOnboardingStatus.mockResolvedValue({
      completed: false,
      active_filter_count: 0,
    });
  });

  it("renders the onboarding form with textarea", () => {
    renderWithProviders(<OnboardingPage />);
    expect(
      screen.getByPlaceholderText(/mechanistic interpretability/i)
    ).toBeInTheDocument();
  });

  it("submits form and shows running state", async () => {
    mockApi.createOnboardingExtraction.mockResolvedValue({
      id: "ext-1",
      status: "queued",
      input_text: "test",
      proposed_filters: [],
    });
    mockApi.getOnboardingExtraction.mockResolvedValue({
      id: "ext-1",
      status: "running",
      input_text: "test",
      proposed_filters: [],
    });

    renderWithProviders(<OnboardingPage />);

    const textarea = screen.getByPlaceholderText(/mechanistic interpretability/i);
    fireEvent.change(textarea, {
      target: { value: "I study multi-step reasoning in LLMs" },
    });

    const submitBtn = screen.getByRole("button", { name: /generate search filters/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockApi.createOnboardingExtraction).toHaveBeenCalledWith({
        input_text: "I study multi-step reasoning in LLMs",
      });
    });
  });

  it("renders editable proposed filters when extraction completes", async () => {
    const proposedFilters = [
      {
        id: "f1",
        name: "LLM Reasoning",
        description: "LLMs can reason",
        mode: "warrants" as const,
      },
    ];

    mockApi.createOnboardingExtraction.mockResolvedValue({
      id: "ext-1",
      status: "completed",
      input_text: "test",
      proposed_filters: proposedFilters,
    });
    mockApi.getOnboardingExtraction.mockResolvedValue({
      id: "ext-1",
      status: "completed",
      input_text: "test",
      proposed_filters: proposedFilters,
    });

    renderWithProviders(<OnboardingPage />);

    const textarea = screen.getByPlaceholderText(/mechanistic interpretability/i);
    fireEvent.change(textarea, { target: { value: "test" } });
    fireEvent.click(screen.getByRole("button", { name: /generate search filters/i }));

    await waitFor(() => {
      expect(screen.getByText("LLM Reasoning")).toBeInTheDocument();
    });
  });

  it("renders proposed filters while extraction is still running", async () => {
    const proposedFilters = [
      {
        id: "f1",
        name: "Streaming Filter",
        description: "A filter that arrived before completion",
        mode: "relevance" as const,
      },
    ];

    mockApi.createOnboardingExtraction.mockResolvedValue({
      id: "ext-1",
      status: "running",
      input_text: "test",
      proposed_filters: proposedFilters,
    });
    mockApi.getOnboardingExtraction.mockResolvedValue({
      id: "ext-1",
      status: "running",
      input_text: "test",
      proposed_filters: proposedFilters,
    });

    renderWithProviders(<OnboardingPage />);

    const textarea = screen.getByPlaceholderText(/mechanistic interpretability/i);
    fireEvent.change(textarea, { target: { value: "test" } });
    fireEvent.click(screen.getByRole("button", { name: /generate search filters/i }));

    await waitFor(() => {
      expect(screen.getByText("Streaming Filter")).toBeInTheDocument();
      expect(screen.getByText(/filters will appear here/i)).toBeInTheDocument();
    });
  });
});
