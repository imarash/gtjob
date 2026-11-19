import { renderMarkdown } from "@/lib/markdown.mjs";

const CLASS =
  "flex flex-col gap-3 overflow-x-auto text-body-regular text-text-primary [&_a]:underline [&_code]:text-body-2-regular [&_h1]:text-title-3-medium [&_h2]:text-headline-medium [&_h3]:text-body-medium [&_pre]:overflow-x-auto [&_table]:w-full [&_td]:border [&_td]:border-border-table [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-border-table [&_th]:px-2 [&_th]:py-1 [&_ul]:list-disc [&_ul]:ps-5";

export function MarkdownBlock({ markdown }: { markdown: string }) {
  return <div className={CLASS} dangerouslySetInnerHTML={{ __html: renderMarkdown(markdown) }} />;
}
