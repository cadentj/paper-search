import { redirect } from "next/navigation";

export default function DashboardOnboardingPage() {
  redirect("/dashboard/filters");
}
