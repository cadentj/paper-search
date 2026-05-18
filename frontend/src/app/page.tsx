"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useOnboardingStatus } from "@/hooks/use-queries";

export default function Home() {
  const router = useRouter();
  const { data, isLoading } = useOnboardingStatus();

  useEffect(() => {
    if (isLoading) return;
    if (data?.completed) {
      router.replace("/daily");
    } else {
      router.replace("/onboarding");
    }
  }, [data, isLoading, router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-muted-foreground">Loading...</p>
    </div>
  );
}
