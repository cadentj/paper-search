import { describe, it, expect, vi } from "vitest";

const mockRedirect = vi.fn();
vi.mock("next/navigation", () => ({
  redirect: mockRedirect,
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), replace: vi.fn() }),
}));

describe("OnboardingPage", () => {
  it("redirects to filters page", async () => {
    const { default: OnboardingPage } = await import(
      "@/app/onboarding/page"
    );
    try {
      OnboardingPage();
    } catch {
      // redirect throws in Next.js
    }
    expect(mockRedirect).toHaveBeenCalledWith("/dashboard/filters");
  });
});
