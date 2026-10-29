"use client";

import { useState } from "react";
import { Button } from "@/components/base/buttons/button";

export function LivenessCheck({ id, hasUrl }: { id: string; hasUrl: boolean }) {
  const [text, setText] = useState(hasUrl ? "not checked" : "not checked — this row has no posting URL");
  const [pending, setPending] = useState(false);

  return (
    <div className="flex flex-col gap-2">
      <p className="text-body-regular text-text-secondary">Liveness: {text}</p>
      {hasUrl ? (
        <div>
          <Button
            variant="secondary"
            disabled={pending}
            onClick={async () => {
              setPending(true);
              const response = await fetch(`/api/applications/${id}/liveness`, { method: "POST" });
              const body = (await response.json()) as { verdict?: string; error?: string; stderr?: string };
              setPending(false);
              if (!response.ok) {
                setText(body.stderr || body.error || "not checked");
                return;
              }
              setText(body.verdict || "not checked");
            }}
          >
            Check if it is live
          </Button>
        </div>
      ) : null}
    </div>
  );
}
