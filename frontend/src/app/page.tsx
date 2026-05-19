import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Paper Search",
  description: "Keep up with relevant research papers",
};

export default function Home() {
  redirect("/dashboard/filters");
}
