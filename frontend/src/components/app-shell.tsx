"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import {
  Newspaper,
  Filter,
  Settings,
  ListTodo,
  Loader2,
} from "lucide-react";
import { useFeedbackStatus, useJobsOverview } from "@/hooks/use-queries";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarProvider,
  SidebarInset,
} from "@/components/ui/sidebar";
import { type ReactNode } from "react";

const SETTINGS_HREF = "/dashboard/settings";
const JOBS_HREF = "/dashboard/jobs";

const DAILY_SUB_ITEMS = [
  { label: "Report", href: "/dashboard/daily/report" },
  { label: "All Papers", href: "/dashboard/daily/all-papers" },
] as const;

const REPORT_JOB_KINDS = new Set(["daily_search", "daily_search_summary"]);

function isDailyPath(pathname: string) {
  return pathname === "/dashboard/daily" || pathname.startsWith("/dashboard/daily/");
}

function isDailyReportPath(pathname: string) {
  return pathname === "/dashboard/daily" || pathname === "/dashboard/daily/report";
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { data: feedbackStatus } = useFeedbackStatus();
  const { data: jobsOverview } = useJobsOverview();

  const activeJobs = jobsOverview?.active ?? [];
  const hasActiveJobs = activeJobs.length > 0;
  const hasReportJob = activeJobs.some((entry) => REPORT_JOB_KINDS.has(entry.job.kind));
  const ideaMapCount = activeJobs.filter((entry) => entry.job.kind === "idea_map").length;

  const hasPendingFeedback = feedbackStatus
    ? feedbackStatus.pending_votes > 0 || feedbackStatus.pending_notes > 0
    : false;
  const hasPendingProposals = feedbackStatus
    ? feedbackStatus.pending_proposals > 0
    : false;

  return (
    <SidebarProvider>
      <Sidebar>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>Paper Search</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    isActive={pathname === "/dashboard/filters"}
                    render={<Link href="/dashboard/filters" />}
                  >
                    <Filter className="size-4" />
                    <span>Filters</span>
                    {hasPendingProposals && (
                      <span className="ml-auto inline-flex size-2 rounded-full bg-green-500" />
                    )}
                    {!hasPendingProposals && hasPendingFeedback && (
                      <span className="ml-auto inline-flex size-2 rounded-full bg-blue-500" />
                    )}
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    isActive={isDailyPath(pathname)}
                    render={<Link href="/dashboard/daily/report" />}
                  >
                    <Newspaper className="size-4" />
                    <span>Daily</span>
                    {ideaMapCount > 0 && (
                      <span className="ml-auto rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium tabular-nums">
                        {ideaMapCount}
                      </span>
                    )}
                  </SidebarMenuButton>
                  <SidebarMenuSub>
                    {DAILY_SUB_ITEMS.map((item) => (
                      <SidebarMenuSubItem key={item.href}>
                        <SidebarMenuSubButton
                          isActive={
                            item.href === "/dashboard/daily/report"
                              ? isDailyReportPath(pathname)
                              : pathname === item.href
                          }
                          render={<Link href={item.href} />}
                        >
                          {item.label}
                          {item.href === "/dashboard/daily/report" && hasReportJob && (
                            <Loader2 className="ml-auto size-3.5 animate-spin text-muted-foreground" />
                          )}
                        </SidebarMenuSubButton>
                      </SidebarMenuSubItem>
                    ))}
                  </SidebarMenuSub>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    isActive={pathname === JOBS_HREF}
                    render={<Link href={JOBS_HREF} />}
                  >
                    <ListTodo className="size-4" />
                    <span>Jobs</span>
                    {hasActiveJobs && (
                      <Loader2 className="ml-auto size-3.5 animate-spin text-muted-foreground" />
                    )}
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    isActive={pathname === SETTINGS_HREF}
                    render={<Link href={SETTINGS_HREF} />}
                  >
                    <Settings className="size-4" />
                    <span>Settings</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
      </Sidebar>
      <SidebarInset>{children}</SidebarInset>
    </SidebarProvider>
  );
}
