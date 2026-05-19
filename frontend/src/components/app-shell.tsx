"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Newspaper,
  Search,
  Filter,
  Settings,
} from "lucide-react";
import { api } from "@/lib/api";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarInset,
} from "@/components/ui/sidebar";
import { type ReactNode } from "react";

const NAV_ITEMS = [
  { label: "Daily", href: "/dashboard/daily", icon: Newspaper },
  { label: "Filters", href: "/dashboard/filters", icon: Filter },
  { label: "Search", href: "/dashboard/search", icon: Search },
  { label: "Settings", href: "/dashboard/settings", icon: Settings },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [feedbackCount, setFeedbackCount] = useState(0);

  useEffect(() => {
    api.getFeedbackNotifications()
      .then((data) => setFeedbackCount(data.unseen_count))
      .catch(() => {});
  }, [pathname]);

  return (
    <SidebarProvider>
      <Sidebar>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>Paper Search</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {NAV_ITEMS.map((item) => (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      isActive={pathname === item.href}
                      render={<Link href={item.href} />}
                    >
                      <item.icon className="size-4" />
                      <span>{item.label}</span>
                      {item.label === "Filters" && feedbackCount > 0 && (
                        <span className="ml-auto inline-flex size-2 rounded-full bg-blue-500" />
                      )}
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
      </Sidebar>
      <SidebarInset>{children}</SidebarInset>
    </SidebarProvider>
  );
}
