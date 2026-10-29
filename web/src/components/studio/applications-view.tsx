"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Tab, TabList, TabPanel, Tabs } from "@/components/base/tabs/tabs";

export function ApplicationsView({
  view,
  query,
  table,
  board,
}: {
  view: "table" | "board";
  query: string;
  table: ReactNode;
  board: ReactNode;
}) {
  const router = useRouter();
  const suffix = query ? `&q=${encodeURIComponent(query)}` : "";
  return (
    <Tabs
      selectedKey={view}
      onSelectionChange={(key) => {
        if (key === "board") router.push(`/applications?view=board${suffix}`);
        else router.push(query ? `/applications?q=${encodeURIComponent(query)}` : "/applications");
      }}
    >
      <TabList aria-label="Applications">
        <Tab id="table">Table</Tab>
        <Tab id="board">Board</Tab>
      </TabList>
      <TabPanel id="table">{table}</TabPanel>
      <TabPanel id="board">{board}</TabPanel>
    </Tabs>
  );
}
