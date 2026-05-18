"use client";

import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Newspaper,
  Search,
  Filter,
  RotateCcw,
  Settings,
} from "lucide-react";
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
  SidebarFooter,
} from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import { useResetOnboarding } from "@/hooks/use-queries";
import { type ReactNode } from "react";

const NAV_ITEMS = [
  { label: "Daily", href: "/dashboard/daily", icon: Newspaper },
  { label: "Filters", href: "/dashboard/filters", icon: Filter },
  { label: "Search", href: "/dashboard/search", icon: Search },
  { label: "Settings", href: "/dashboard/settings", icon: Settings },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { push } = useRouter();
  const resetMutation = useResetOnboarding();

  const handleReset = async () => {
    if (!confirm("Reset all onboarding, filters, and search data?")) return;
    await resetMutation.mutateAsync();
    push("/dashboard/filters");
  };

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
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start text-muted-foreground"
            onClick={handleReset}
            disabled={resetMutation.isPending}
          >
            <RotateCcw className="mr-2 size-3" />
            {resetMutation.isPending ? "Resetting…" : "Dev Reset"}
          </Button>
        </SidebarFooter>
      </Sidebar>
      <SidebarInset>{children}</SidebarInset>
    </SidebarProvider>
  );
}
