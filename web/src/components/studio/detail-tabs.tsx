"use client";

import type { ReactNode } from "react";
import { Tab, TabList, TabPanel, Tabs } from "@/components/base/tabs/tabs";

export function DetailTabs({
  overview,
  documents,
  activity,
}: {
  overview: ReactNode;
  documents: ReactNode;
  activity: ReactNode;
}) {
  return (
    <Tabs defaultSelectedKey="overview">
      <TabList aria-label="Application">
        <Tab id="overview">Overview</Tab>
        <Tab id="documents">Documents</Tab>
        <Tab id="activity">Activity</Tab>
      </TabList>
      <TabPanel id="overview">{overview}</TabPanel>
      <TabPanel id="documents">{documents}</TabPanel>
      <TabPanel id="activity">{activity}</TabPanel>
    </Tabs>
  );
}
