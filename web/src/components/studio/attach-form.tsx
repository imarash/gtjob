"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/base/buttons/button";
import { Select, SelectItem } from "@/components/base/select/select";

export function AttachForm({
  slug,
  rows,
}: {
  slug: string;
  rows: { num: string; company: string; role: string }[];
}) {
  const router = useRouter();
  const [row, setRow] = useState(rows[0]?.num ?? "");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  if (rows.length === 0) {
    return <p className="text-body-regular text-text-secondary">The tracker has no rows to attach.</p>;
  }

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={async (event) => {
        event.preventDefault();
        setPending(true);
        setError("");
        const response = await fetch(`/api/runs/${slug}/attach`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ row }),
        });
        const body = (await response.json()) as { error?: string; stderr?: string };
        setPending(false);
        if (!response.ok) {
          setError(body.stderr || body.error || "The run was not attached.");
          return;
        }
        router.refresh();
      }}
    >
      <Select
        aria-label="Application"
        selectedKey={row}
        onSelectionChange={(key) => {
          if (typeof key === "string") setRow(key);
        }}
      >
        {rows.map((item) => (
          <SelectItem key={item.num} id={item.num}>
            {`#${item.num} ${item.company} — ${item.role}`}
          </SelectItem>
        ))}
      </Select>
      {error ? (
        <pre className="whitespace-pre-wrap text-body-2-regular text-text-error-primary">{error}</pre>
      ) : null}
      <div>
        <Button type="submit" disabled={pending || row === ""}>
          Attach to application
        </Button>
      </div>
    </form>
  );
}
