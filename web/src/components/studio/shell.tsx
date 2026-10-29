"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { RiFileList3Line, RiHomeLine, RiKanbanView2 } from "@remixicon/react";
import { DashboardSidebar } from "@/components/application/dashboard/dashboard-sidebar";
import { DirectionProvider } from "@/components/foundations/direction/direction";
import { ScrollFade, useScrollFade } from "@/components/foundations/scroll-fade/scroll-fade";

const NAV = [
  { key: "today", label: "Today", icon: RiHomeLine, href: "/" },
  { key: "applications", label: "Applications", icon: RiKanbanView2, href: "/applications" },
  { key: "runs", label: "Runs", icon: RiFileList3Line, href: "/runs" },
];

function selectedKey(pathname: string) {
  if (pathname.startsWith("/applications")) return "applications";
  if (pathname.startsWith("/runs")) return "runs";
  if (pathname.startsWith("/settings")) return "settings";
  return "today";
}

export function StudioShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const fade = useScrollFade();
  return (
    <DirectionProvider locale="en-US">
      <div className="flex h-dvh gap-3 bg-background-full p-3">
        <DashboardSidebar selected={selectedKey(pathname)} items={NAV} className="h-full" />
        <div className="relative min-h-0 min-w-0 flex-1">
          <main
            onScroll={fade.onScroll}
            className="h-full overflow-y-auto rounded-3xl border border-border-button-default bg-background-primary-default"
          >
            <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 p-6">{children}</div>
          </main>
          <ScrollFade progress={fade.progress} surfaceClassName="from-background-primary-default" />
        </div>
      </div>
    </DirectionProvider>
  );
}
