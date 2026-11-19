import type { Metadata } from "next";
import { Suspense } from "react";
import { StudioShell } from "@/components/studio/shell";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "gtjob Studio",
  description: "Today, applications, and tailored CV runs on this machine.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <body className="min-h-full bg-background-full">
        <StudioShell>
          <Suspense
            fallback={<p className="text-body-regular text-text-secondary">Loading</p>}
          >
            {children}
          </Suspense>
        </StudioShell>
      </body>
    </html>
  );
}
