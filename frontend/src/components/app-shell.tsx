"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Newspaper,
  Filter,
  Settings,
} from "lucide-react";
import { api } from "@/lib/api";
import type { FeedbackStatus } from "@/lib/api";
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

const DAILY_SUB_ITEMS = [
  { label: "Report", href: "/dashboard/daily/report" },
  { label: "All Papers", href: "/dashboard/daily/all-papers" },
] as const;

function isDailyPath(pathname: string) {
  return pathname === "/dashboard/daily" || pathname.startsWith("/dashboard/daily/");
}

function isDailyReportPath(pathname: string) {
  return pathname === "/dashboard/daily" || pathname === "/dashboard/daily/report";
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [feedbackStatus, setFeedbackStatus] = useState<FeedbackStatus | null>(null);

  useEffect(() => {
    api.getFeedbackStatus()
      .then(setFeedbackStatus)
      .catch(() => {});
  }, [pathname]);

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
                        </SidebarMenuSubButton>
                      </SidebarMenuSubItem>
                    ))}
                  </SidebarMenuSub>
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
