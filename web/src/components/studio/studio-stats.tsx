"use client";

import { RiBriefcaseLine, RiCalendarCheckLine, RiFileList3Line, RiTrophyLine } from "@remixicon/react";
import { StatCards } from "@/components/application/dashboard/stat-cards";

export function StudioStats({
  applications,
  interview,
  offers,
  runs,
  applicationsDelta,
}: {
  applications: string;
  interview: string;
  offers: string;
  runs: string;
  applicationsDelta: string;
}) {
  return (
    <StatCards
      stats={[
        {
          icon: RiBriefcaseLine,
          label: "Applications",
          value: applications,
          delta: applicationsDelta,
          deltaColor: "neutral",
        },
        {
          icon: RiCalendarCheckLine,
          label: "Interview",
          value: interview,
          delta: "now",
          deltaColor: "neutral",
        },
        {
          icon: RiTrophyLine,
          label: "Offers",
          value: offers,
          delta: "open",
          deltaColor: "neutral",
        },
        {
          icon: RiFileList3Line,
          label: "Tailored runs",
          value: runs,
          delta: "on disk",
          deltaColor: "neutral",
        },
      ]}
    />
  );
}
