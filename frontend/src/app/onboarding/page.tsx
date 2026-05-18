import type { Metadata } from "next";
import { OnboardingClient } from "./onboarding-client";

export const metadata: Metadata = {
  title: "Onboarding | Paper Search",
  description: "Set up personalized research paper filters",
};

export default function OnboardingPage() {
  return <OnboardingClient />;
}
