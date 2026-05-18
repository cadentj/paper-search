import type { Metadata } from "next";
import { redirect } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const metadata: Metadata = {
  title: "Paper Search",
  description: "Keep up with relevant research papers",
};

async function getOnboardingCompleted() {
  try {
    const response = await fetch(`${API_URL}/onboarding/status`, {
      cache: "no-store",
    });
    if (!response.ok) return false;
    const status = (await response.json()) as { completed?: boolean };
    return status.completed === true;
  } catch {
    return false;
  }
}

export default async function Home() {
  if (await getOnboardingCompleted()) {
    redirect("/dashboard/daily");
  }
  redirect("/dashboard/onboarding");
}
