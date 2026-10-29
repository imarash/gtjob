"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/base/buttons/button";
import { Select, SelectItem } from "@/components/base/select/select";
import { Textarea } from "@/components/base/textarea/textarea";
import { QuestionFields, type StudioQuestion } from "@/components/studio/question-fields";
import { buildAnswerRequest, initialPicked } from "@/lib/answer-select.mjs";

type Envelope = {
  ok?: boolean;
  command?: string;
  run?: string;
  stage?: string;
  next_action?: string;
  error?: { message?: string; hint?: string };
  data?: Record<string, unknown>;
};

type CallResult = {
  envelope: Envelope | null;
  stdout: string;
  stderr: string;
  error: string;
};

async function callTool(body: Record<string, unknown>): Promise<CallResult> {
  const response = await fetch("/api/cvt", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = (await response.json()) as {
    envelope?: Envelope | null;
    stdout?: string;
    stderr?: string;
    error?: string;
    followup?: Envelope | null;
  };
  if (!response.ok) {
    return { envelope: payload.envelope ?? null, stdout: "", stderr: payload.stderr || "", error: payload.error || "The command failed." };
  }
  const follow = payload.followup;
  const envelope = payload.envelope ?? null;
  const stderr = [payload.stderr, follow && !follow.ok ? follow.error?.message : ""].filter(Boolean).join("\n");
  return {
    envelope: follow ? { ...envelope, stage: follow.stage || envelope?.stage, next_action: follow.next_action || envelope?.next_action } : envelope,
    stdout: payload.stdout || "",
    stderr,
    error: "",
  };
}

export function CvtResult({ result }: { result: CallResult | null }) {
  if (!result) return null;
  if (result.error) return <p className="text-body-regular text-text-error-primary">{result.error}</p>;
  const envelope = result.envelope;
  if (!envelope && result.stdout) {
    return <pre className="whitespace-pre-wrap text-body-2-regular text-text-primary">{result.stdout}</pre>;
  }
  if (!envelope) return <p className="text-body-regular text-text-secondary">No JSON came back.</p>;
  const data = envelope.data ?? {};
  const counts = data.counts && typeof data.counts === "object" ? JSON.stringify(data.counts) : "";
  const items = Array.isArray(data.items) ? data.items : [];
  const runs = Array.isArray(data.runs) ? data.runs : [];
  const seen = new Set<string>();
  const uniqueRuns = runs.filter((item) => {
    const slug = (item as { run_slug?: string }).run_slug || "";
    if (!slug || seen.has(slug)) return false;
    seen.add(slug);
    return true;
  });
  const plan = data.plan && typeof data.plan === "object" ? (data.plan as Record<string, unknown>) : null;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-body-regular text-text-primary">
        {envelope.ok === false ? envelope.error?.message || "cvt reported an error." : envelope.stage || envelope.command}
        {envelope.run ? ` · ${envelope.run}` : ""}
      </p>
      {envelope.next_action ? <p className="text-body-regular text-text-secondary">{envelope.next_action}</p> : null}
      {envelope.error?.hint ? <p className="text-body-regular text-text-secondary">{envelope.error.hint}</p> : null}
      {uniqueRuns.length > 0 ? (
        <ul className="flex flex-col gap-1">
          {uniqueRuns.map((item) => {
            const row = item as { run_slug?: string; stage?: string; status?: string };
            return (
              <li key={row.run_slug} className="text-body-2-regular text-text-primary">
                {row.run_slug} · {row.stage}
                {row.status ? ` · ${row.status}` : ""}
              </li>
            );
          })}
        </ul>
      ) : null}
      {counts ? <p className="text-body-2-regular text-text-secondary">Changes: {counts}</p> : null}
      {items.length > 0 ? (
        <ul className="flex flex-col gap-1">
          {items.slice(0, 30).map((item, index) => (
            <li key={index} className="text-body-2-regular text-text-primary">
              {typeof item === "string" ? item : JSON.stringify(item)}
            </li>
          ))}
        </ul>
      ) : null}
      {plan ? (
        <pre className="whitespace-pre-wrap text-body-2-regular text-text-primary">
          {JSON.stringify(plan, null, 2).slice(0, 12_000)}
        </pre>
      ) : null}
      {result.stderr ? <pre className="whitespace-pre-wrap text-body-2-regular text-text-secondary">{result.stderr}</pre> : null}
    </div>
  );
}

function useCall() {
  const [result, setResult] = useState<CallResult | null>(null);
  const [pending, setPending] = useState(false);
  async function run(body: Record<string, unknown>) {
    setPending(true);
    setResult(await callTool(body));
    setPending(false);
  }
  return { result, pending, run };
}

export function StatusButton({ run, all }: { run?: string; all?: boolean }) {
  const { result, pending, run: call } = useCall();
  return (
    <div className="flex flex-col gap-3">
      <div>
        <Button disabled={pending} onClick={() => call({ command: "status", run, all: Boolean(all) })}>
          {all ? "Show every run" : "Where this run stands"}
        </Button>
      </div>
      <CvtResult result={result} />
    </div>
  );
}

export function StartRunForm({ cvs, jds }: { cvs: string[]; jds: string[] }) {
  const router = useRouter();
  const [cv, setCv] = useState(cvs[0] ?? "");
  const [jd, setJd] = useState(jds[0] ?? "");
  const [jdText, setJdText] = useState("");
  const [template, setTemplate] = useState("modern");
  const { result, pending, run } = useCall();
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={async (event) => {
        event.preventDefault();
        await run({
          command: "init",
          cv,
          jd: jdText.trim() ? "" : jd,
          jdText: jdText.trim(),
          template,
        });
        router.refresh();
      }}
    >
      <p className="text-body-regular text-text-secondary">
        This creates the run and extracts the text. Profile, match, and the tailor plan still happen in Claude.
        Studio does not call a model.
      </p>
      {cvs.length === 0 ? (
        <p className="text-body-regular text-text-secondary">Put a PDF or text CV in CVs/ first.</p>
      ) : (
        <Select aria-label="CV" selectedKey={cv} onSelectionChange={(key) => typeof key === "string" && setCv(key)}>
          {cvs.map((name) => (
            <SelectItem key={name} id={name}>
              {name}
            </SelectItem>
          ))}
        </Select>
      )}
      {jds.length > 0 ? (
        <Select aria-label="Job description file" selectedKey={jd} onSelectionChange={(key) => typeof key === "string" && setJd(key)}>
          {jds.map((name) => (
            <SelectItem key={name} id={name}>
              {name}
            </SelectItem>
          ))}
        </Select>
      ) : null}
      <Textarea aria-label="Job text" label="Or paste the job" value={jdText} onChange={setJdText} rows={6} />
      <Select aria-label="Template" selectedKey={template} onSelectionChange={(key) => typeof key === "string" && setTemplate(key)}>
        {["modern", "classic", "sidebar"].map((name) => (
          <SelectItem key={name} id={name}>
            {name}
          </SelectItem>
        ))}
      </Select>
      <div>
        <Button type="submit" disabled={pending || !cv}>
          Start run
        </Button>
      </div>
      <CvtResult result={result} />
    </form>
  );
}

export function PolishForm({ cvs }: { cvs: string[] }) {
  const [cv, setCv] = useState(cvs[0] ?? "");
  const { result, pending, run } = useCall();
  return (
    <div className="flex flex-col gap-3">
      <p className="text-body-regular text-text-secondary">
        Extract uses the same reader as ingest. Rendering every template still needs the model JSON from Claude.
      </p>
      {cvs.length === 0 ? (
        <p className="text-body-regular text-text-secondary">Put a CV in CVs/ first.</p>
      ) : (
        <Select aria-label="CV" selectedKey={cv} onSelectionChange={(key) => typeof key === "string" && setCv(key)}>
          {cvs.map((name) => (
            <SelectItem key={name} id={name}>
              {name}
            </SelectItem>
          ))}
        </Select>
      )}
      <div>
        <Button disabled={pending || !cv} onClick={() => run({ command: "polish-extract", cv })}>
          Extract text
        </Button>
      </div>
      <CvtResult result={result} />
    </div>
  );
}

export function AttestPanel({ runs }: { runs: string[] }) {
  const [runSlug, setRunSlug] = useState(runs[0] ?? "latest");
  const [id, setId] = useState("");
  const [confirm, setConfirm] = useState(false);
  const { result, pending, run } = useCall();
  return (
    <div className="flex flex-col gap-3">
      <p className="text-body-regular text-text-secondary">
        Confirmed facts live in profiles/. Revoking one means later runs will not use it.
      </p>
      {runs.length > 0 ? (
        <Select aria-label="Run" selectedKey={runSlug} onSelectionChange={(key) => typeof key === "string" && setRunSlug(key)}>
          {runs.map((slug) => (
            <SelectItem key={slug} id={slug}>
              {slug}
            </SelectItem>
          ))}
        </Select>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button disabled={pending} onClick={() => run({ command: "attest", action: "list", run: runSlug })}>
          List
        </Button>
        <Button disabled={pending || !id} onClick={() => run({ command: "attest", action: "show", id, run: runSlug })}>
          Show
        </Button>
      </div>
      <label className="flex flex-col gap-1 text-body-2-regular text-text-secondary">
        Attestation id
        <input
          className="rounded-xl border border-border-button-default bg-background-primary-default px-3 py-2 text-body-regular text-text-primary"
          value={id}
          onChange={(event) => setId(event.target.value.trim())}
          placeholder="att-001"
        />
      </label>
      {confirm ? (
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" disabled={pending || !id} onClick={() => run({ command: "attest", action: "revoke", id, run: runSlug })}>
            Revoke {id}
          </Button>
          <Button variant="secondary" disabled={pending || !id} onClick={() => run({ command: "attest", action: "activate", id, run: runSlug })}>
            Activate {id}
          </Button>
        </div>
      ) : (
        <div>
          <Button variant="secondary" onClick={() => setConfirm(true)}>
            Change an attestation
          </Button>
        </div>
      )}
      <CvtResult result={result} />
    </div>
  );
}

export function RunActions({ slug }: { slug: string }) {
  const router = useRouter();
  const [result, setResult] = useState<CallResult | null>(null);
  const [pending, setPending] = useState(false);
  const [questions, setQuestions] = useState<StudioQuestion[]>([]);
  const [picked, setPicked] = useState<Record<string, string[]>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [approveArmed, setApproveArmed] = useState(false);
  const [template, setTemplate] = useState("modern");

  async function execute(body: Record<string, unknown>) {
    setPending(true);
    const next = await callTool(body);
    setResult(next);
    setPending(false);
    return next;
  }

  return (
    <div className="flex flex-col gap-4">
      <StatusButton run={slug} />
      <div className="flex flex-wrap gap-2">
        <Button
          disabled={pending}
          onClick={async () => {
            const next = await execute({ command: "questions", run: slug });
            const render = next.envelope?.data?.render as { questions?: StudioQuestion[] } | undefined;
            const list = Array.isArray(render?.questions) ? render.questions : [];
            setQuestions(list);
            setPicked(initialPicked(list));
            setNotes({});
            router.refresh();
          }}
        >
          Load questions
        </Button>
        <Button disabled={pending} onClick={() => execute({ command: "diff", run: slug })}>
          Show changes
        </Button>
        <Button disabled={pending} onClick={() => execute({ command: "fit", run: slug })}>
          Fit pages
        </Button>
        <Button disabled={pending} onClick={() => execute({ command: "validate", run: slug })}>
          Validate
        </Button>
        <Button disabled={pending} onClick={() => execute({ command: "report", run: slug })}>
          Write report
        </Button>
        <Button disabled={pending} onClick={() => execute({ command: "ingest", run: slug })}>
          Extract inputs
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Select aria-label="Template" selectedKey={template} onSelectionChange={(key) => typeof key === "string" && setTemplate(key)}>
          {["modern", "classic", "sidebar"].map((name) => (
            <SelectItem key={name} id={name}>
              {name}
            </SelectItem>
          ))}
        </Select>
        <Button disabled={pending} onClick={() => execute({ command: "render", run: slug, template })}>
          Render
        </Button>
      </div>
      {questions.length > 0 ? (
        <form
          className="flex flex-col gap-3"
          onSubmit={async (event) => {
            event.preventDefault();
            const plan = buildAnswerRequest(questions, picked, notes);
            if (plan.prose) {
              setResult({
                envelope: null,
                stdout: "",
                stderr: "",
                error: "A written answer continues in the toolbox conversation, where Cursor parses it.",
              });
              return;
            }
            await execute({
              command: "answers-apply",
              run: slug,
              mode: "dry-run",
              auto: plan.auto,
              select: plan.select,
              defaultRest: plan.defaultRest,
            });
          }}
        >
          <QuestionFields
            questions={questions}
            picked={picked}
            notes={notes}
            onToggle={(id, choiceId, on, kind) =>
              setPicked((current) => {
                if (kind === "single") return { ...current, [id]: on ? [choiceId] : [] };
                const list = current[id] || [];
                const next = on ? [...list, choiceId] : list.filter((item) => item !== choiceId);
                return { ...current, [id]: [...new Set(next)] };
              })
            }
            onNote={(id, text) => setNotes((current) => ({ ...current, [id]: text }))}
          />
          <p className="text-body-2-regular text-text-secondary">
            Several items can be checked on one question. A written answer continues in the toolbox conversation.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={pending}>
              Preview answers
            </Button>
            <Button
              variant="secondary"
              disabled={pending}
              onClick={() => {
                const plan = buildAnswerRequest(questions, picked, notes);
                if (plan.prose) {
                  setResult({
                    envelope: null,
                    stdout: "",
                    stderr: "",
                    error: "A written answer continues in the toolbox conversation, where Cursor parses it.",
                  });
                  return;
                }
                void execute({
                  command: "answers-apply",
                  run: slug,
                  mode: "commit",
                  auto: plan.auto,
                  select: plan.select,
                  defaultRest: plan.defaultRest,
                });
              }}
            >
              Apply answers
            </Button>
          </div>
        </form>
      ) : null}
      {approveArmed ? (
        <Button
          variant="secondary"
          disabled={pending}
          onClick={async () => {
            await execute({ command: "approve", run: slug });
            setApproveArmed(false);
            router.refresh();
          }}
        >
          Approve this run
        </Button>
      ) : (
        <div>
          <Button variant="secondary" onClick={() => setApproveArmed(true)}>
            Approve…
          </Button>
        </div>
      )}
      <CvtResult result={result} />
    </div>
  );
}

export function RunPicker({ runs }: { runs: string[] }) {
  const [slug, setSlug] = useState(runs[0] ?? "");
  if (runs.length === 0) {
    return <p className="text-body-regular text-text-secondary">No tailored run is on disk yet.</p>;
  }
  return (
    <div className="flex flex-col gap-4">
      <Select aria-label="Run" selectedKey={slug} onSelectionChange={(key) => typeof key === "string" && setSlug(key)}>
        {runs.map((item) => (
          <SelectItem key={item} id={item}>
            {item}
          </SelectItem>
        ))}
      </Select>
      {slug ? <RunActions slug={slug} /> : null}
    </div>
  );
}
