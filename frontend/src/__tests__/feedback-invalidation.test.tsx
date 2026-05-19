import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useSubmitMatchFeedback } from "@/hooks/use-queries";

const mockApi = vi.hoisted(() => ({
  submitMatchFeedback: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: mockApi,
}));

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe("feedback status invalidation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.submitMatchFeedback.mockResolvedValue({
      id: "fb-1",
      paper_id: "paper-1",
      value: "up",
    });
  });

  it("invalidates feedback status after match feedback submission", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useSubmitMatchFeedback(), {
      wrapper: wrapper(queryClient),
    });

    await result.current.mutateAsync({ matchId: "match-1", value: "up" });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ["feedback", "status"],
      });
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ["feedback", "items", "pending"],
      });
    });
  });
});
