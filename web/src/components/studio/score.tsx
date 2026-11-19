import { Chip } from "@/components/base/badges/chip";
import { belowApplyBar, columnForStatus } from "@/lib/columns.mjs";

const COLUMN_COLOR = {
  review: "yellow",
  progress: "blue",
  interview: "cyan",
  offer: "lime",
  closed: "neutral",
  other: "gray",
} as const;

export function StatusChip({ status }: { status: string }) {
  const column = columnForStatus(status);
  const color = COLUMN_COLOR[column.id as keyof typeof COLUMN_COLOR] ?? "gray";
  return <Chip color={color}>{status || "—"}</Chip>;
}

export function ScoreValue({ score }: { score: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-body-medium text-text-primary">{score || "—"}</span>
      {belowApplyBar(score) ? <Chip color="rose">Do not apply</Chip> : null}
    </span>
  );
}
