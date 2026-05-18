"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  Newspaper,
  Search,
  Filter,
  RotateCcw,
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
  { label: "Daily", href: "/daily", icon: Newspaper },
  { label: "Search", href: "/search", icon: Search },
  { label: "Filters", href: "/filters", icon: Filter },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const resetMutation = useResetOnboarding();

  const handleReset = async () => {
    if (!confirm("Reset all onboarding, filters, and search data?")) return;
    await resetMutation.mutateAsync();
    router.push("/onboarding");
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
                      onClick={() => router.push(item.href)}
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
            {resetMutation.isPending ? "Resetting..." : "Dev Reset"}
          </Button>
        </SidebarFooter>
      </Sidebar>
      <SidebarInset>{children}</SidebarInset>
    </SidebarProvider>
  );
}
