"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/base/buttons/button";
import { Select, SelectItem } from "@/components/base/select/select";

export function StatusForm({
  id,
  status,
  labels,
}: {
  id: string;
  status: string;
  labels: string[];
}) {
  const router = useRouter();
  const [next, setNext] = useState(status);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={async (event) => {
        event.preventDefault();
        setPending(true);
        setError("");
        const response = await fetch(`/api/applications/${id}/status`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ status: next }),
        });
        const body = (await response.json()) as { error?: string; stderr?: string };
        setPending(false);
        if (!response.ok) {
          setError(body.stderr || body.error || "Status was not changed.");
          return;
        }
        router.refresh();
      }}
    >
      <Select
        aria-label="Status"
        selectedKey={next}
        onSelectionChange={(key) => {
          if (typeof key === "string") setNext(key);
        }}
      >
        {labels.map((label) => (
          <SelectItem key={label} id={label}>
            {label}
          </SelectItem>
        ))}
      </Select>
      {error ? (
        <pre className="whitespace-pre-wrap text-body-2-regular text-text-error-primary">{error}</pre>
      ) : null}
      <div>
        <Button type="submit" disabled={pending || next === status}>
          Update status
        </Button>
      </div>
    </form>
  );
}
