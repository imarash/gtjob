"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/base/buttons/button";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "@/components/base/modal/modal";
import { Textarea } from "@/components/base/textarea/textarea";

export function AddRoleDialog() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  return (
    <>
      <Button onClick={() => setOpen(true)}>Add a role</Button>
      <Modal size="lg" isOpen={open} onOpenChange={setOpen}>
        {({ close }) => (
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              setPending(true);
              setError("");
              const response = await fetch("/api/inbox", {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({ text }),
              });
              const body = (await response.json()) as { error?: string };
              setPending(false);
              if (!response.ok) {
                setError(body.error || "Could not save that.");
                return;
              }
              setText("");
              close();
              router.refresh();
            }}
          >
            <ModalHeader
              title="Add a role"
              description="Paste a URL or the job text. Studio stores it here and does not score it."
            />
            <ModalBody>
              <Textarea
                aria-label="URL or job text"
                label="URL or job text"
                value={text}
                onChange={setText}
                rows={8}
                placeholder="https://example.com/jobs/1"
              />
              {error ? <p className="text-body-regular text-text-error-primary">{error}</p> : null}
            </ModalBody>
            <ModalFooter>
              <Button variant="secondary" onClick={close} disabled={pending}>
                Cancel
              </Button>
              <Button type="submit" disabled={pending || text.trim() === ""}>
                Save
              </Button>
            </ModalFooter>
          </form>
        )}
      </Modal>
    </>
  );
}
