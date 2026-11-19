"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { StatusDot } from "@/components/base/badges/status-dot";
import { Button } from "@/components/base/buttons/button";
import { Textarea } from "@/components/base/textarea/textarea";
import { MarkdownBlock } from "@/components/studio/markdown-block";
import { QuestionFields, type PriorAnswer, type StudioQuestion } from "@/components/studio/question-fields";
import { ScrollFade, useScrollFade } from "@/components/foundations/scroll-fade/scroll-fade";
import { applyFailure, initialPicked, pendingReply } from "@/lib/answer-select.mjs";
import { turnsFromLog } from "@/lib/infer-transcript.mjs";
import { providerStatus } from "@/lib/provider-hint.mjs";
import { STEP_LABELS } from "@/lib/stage-copy.mjs";
import { ProviderSelect } from "@/components/studio/provider-select";
import { cx } from "@/utils/cx";

type Turn = {
  id: string;
  role: string;
  name?: string;
  status?: string;
  text?: string;
  detail?: string;
};

type InferStatus = {
  phase?: string;
  message?: string;
  log?: string[];
  turns?: Turn[];
  stage?: string;
  mode?: string;
  updatedAt?: string;
};

type RunProgress = {
  stage?: string;
  title?: string;
  detail?: string;
  step?: number;
  steps?: string[];
  label?: string;
};

const FILL = ["w-1/5", "w-2/5", "w-3/5", "w-4/5", "w-full"];

function elapsedLabel(ms: number) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  if (minutes === 0) return `${seconds}s so far`;
  return `${minutes}m ${String(seconds).padStart(2, "0")}s so far`;
}

function WaitCard({
  title,
  detail,
  steps,
  step,
  elapsed,
}: {
  title: string;
  detail: string;
  steps: string[];
  step: number;
  elapsed: string;
}) {
  const counted = Math.max(steps.length, 1);
  const current = Math.min(Math.max(step, 0), counted - 1);
  return (
    <div
      className="flex flex-col gap-3 rounded-xl bg-background-secondary-default p-4"
      role="progressbar"
      aria-label="Tailoring progress"
      aria-valuemin={1}
      aria-valuemax={counted}
      aria-valuenow={current + 1}
      aria-valuetext={title}
    >
      <div>
        <p className="text-body-medium text-text-primary" role="status">
          {title}
        </p>
        <p className="mt-1 text-body-regular text-text-secondary">
          {detail} Stay on this page. Previous work keeps this run if you come back later.
        </p>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-background-tertiary-default" aria-hidden>
        <div
          className={cx(
            "h-full rounded-full bg-accent-600 motion-safe:animate-pulse",
            steps.length > 0 ? FILL[Math.min(current, FILL.length - 1)] : "w-2/5",
          )}
        />
      </div>
      {steps.length > 0 ? (
        <ol className="flex flex-wrap gap-x-4 gap-y-2" aria-label="Steps">
          {steps.map((label, index) => {
            const state = index < current ? "done" : index === current ? "current" : "upcoming";
            return (
              <li
                key={label}
                className="flex items-center gap-1.5"
                aria-current={state === "current" ? "step" : undefined}
              >
                {state === "upcoming" ? (
                  <span aria-hidden className="size-3 rounded-full border border-border-button-default" />
                ) : (
                  <StatusDot color={state === "done" ? "green" : "indigo"} className={state === "current" ? "motion-safe:animate-pulse" : ""} />
                )}
                <span
                  className={
                    state === "current"
                      ? "text-body-2-medium text-text-primary"
                      : state === "done"
                        ? "text-body-2-regular text-text-secondary"
                        : "text-body-2-regular text-text-tertiary"
                  }
                >
                  {label}
                </span>
              </li>
            );
          })}
        </ol>
      ) : null}
      <p className="text-body-2-regular text-text-tertiary" aria-hidden>
        {elapsed}
      </p>
    </div>
  );
}

type ReviewItem = {
  id: string;
  section?: string;
  kind?: string;
  before?: string;
  after?: string;
};

type DraftReview = {
  items: ReviewItem[];
  pending: number;
};

export function CursorConnect() {
  const [connected, setConnected] = useState<boolean | null>(null);
  const [loginUrl, setLoginUrl] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let stop = false;
    async function tick() {
      const response = await fetch("/api/infer");
      const payload = (await response.json()) as {
        connected?: boolean;
        login?: { phase?: string; url?: string; message?: string };
      };
      if (stop) return;
      setConnected(Boolean(payload.connected));
      setLoginUrl(payload.login?.url || "");
    }
    void tick();
    const timer = setInterval(() => void tick(), 3000);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, []);

  if (connected !== false) return null;
  return (
    <section className="flex flex-col gap-2 rounded-2xl border border-border-button-default p-4">
      <p className="text-body-regular text-text-primary">
        Connect Cursor to tailor a CV on this machine. The editor login is separate.
      </p>
      {loginUrl ? (
        <a className="text-body-regular text-text-primary underline" href={loginUrl}>
          Open the Cursor login
        </a>
      ) : null}
      <div>
        <Button
          variant="secondary"
          disabled={pending}
          onClick={async () => {
            setPending(true);
            await fetch("/api/infer", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ command: "login" }),
            });
            setPending(false);
          }}
        >
          Connect Cursor
        </Button>
      </div>
    </section>
  );
}

function visibleTurns(job: InferStatus): Turn[] {
  if (Array.isArray(job.turns) && job.turns.length > 0) return job.turns;
  if (Array.isArray(job.log) && job.log.length > 0) return turnsFromLog(job.log);
  return [];
}

export function InferPanel({
  slug,
  mode,
  title,
  stage,
  connected,
  loginUrl,
  provider,
  cursorReady,
  anthropicReady,
  onProvider,
  detail,
  pendingContinue,
  onContinue,
  onConnect,
  onFinished,
  headerAction,
}: {
  slug: string;
  mode: "tailor" | "reply" | "polish";
  title: string;
  stage: string;
  connected: boolean | null;
  loginUrl: string;
  provider: string;
  cursorReady: boolean;
  anthropicReady: boolean;
  onProvider: (next: string) => void;
  detail: string;
  pendingContinue: boolean;
  onContinue: () => void;
  onConnect: () => void;
  onFinished: (slug: string) => void;
  headerAction?: ReactNode;
}) {
  const router = useRouter();
  const [job, setJob] = useState<InferStatus | null>(null);
  const [questions, setQuestions] = useState<StudioQuestion[]>([]);
  const [picked, setPicked] = useState<Record<string, string[]>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [priors, setPriors] = useState<Record<string, PriorAnswer>>({});
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [review, setReview] = useState<DraftReview | null>(null);
  const [questionsLoaded, setQuestionsLoaded] = useState(false);
  const [progress, setProgress] = useState<RunProgress | null>(null);
  const [liveLabel, setLiveLabel] = useState("");
  const [now, setNow] = useState(() => Date.now());
  const onFinishedRef = useRef(onFinished);
  onFinishedRef.current = onFinished;
  const seenPhase = useRef("");
  const fade = useScrollFade();
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    if (!slug) return;
    let stop = false;
    seenPhase.current = "";
    async function tick() {
      const response = await fetch(`/api/infer?run=${encodeURIComponent(slug)}`);
      const payload = (await response.json()) as { status?: InferStatus | null; progress?: RunProgress | null };
      if (stop) return;
      if (payload.progress) {
        setProgress(payload.progress);
        if (payload.progress.label) setLiveLabel(payload.progress.label);
      }
      if (!payload.status) return;
      setJob(payload.status);
      const phase = payload.status.phase || "";
      const token = `${slug}:${phase}`;
      if (!phase || phase === "starting" || phase === "running" || seenPhase.current === token) return;
      seenPhase.current = token;
      if (phase === "finished") onFinishedRef.current(slug);
      else router.refresh();
    }
    void tick();
    const timer = setInterval(() => void tick(), 1000);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, [slug, router]);

  useEffect(() => {
    setLiveLabel("");
    setProgress(null);
  }, [slug]);

  const phaseNow = job?.phase || "";
  const waitingOnRun = phaseNow === "starting" || phaseNow === "running";

  useEffect(() => {
    if (!waitingOnRun) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [waitingOnRun]);

  useEffect(() => {
    if (!waitingOnRun) return;
    const onLeave = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onLeave);
    return () => window.removeEventListener("beforeunload", onLeave);
  }, [waitingOnRun]);

  function keepAnswers(list: StudioQuestion[]) {
    setQuestions(list);
    setPicked((current) => {
      const next = { ...initialPicked(list) };
      for (const question of list) {
        if (Object.prototype.hasOwnProperty.call(current, question.id)) next[question.id] = current[question.id];
      }
      return next;
    });
    setNotes((current) => {
      const next: Record<string, string> = {};
      for (const question of list) {
        if (current[question.id]) next[question.id] = current[question.id];
      }
      return next;
    });
  }

  async function loadPending() {
    const response = await fetch("/api/cvt", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ command: "questions", run: slug }),
    });
    const payload = (await response.json()) as {
      envelope?: { data?: { render?: { questions?: StudioQuestion[] } } };
    };
    const next = payload.envelope?.data?.render?.questions;
    const list = Array.isArray(next) ? next : [];
    return list.filter((question) => !question.status || question.status === "pending");
  }

  async function loadPriors() {
    const response = await fetch("/api/cvt", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ command: "prior-answers", run: slug }),
    });
    const payload = (await response.json()) as { priors?: Record<string, PriorAnswer> };
    const next = payload.priors && typeof payload.priors === "object" ? payload.priors : {};
    setPriors(next);
  }

  function usePrior(id: string) {
    const prior = priors[id];
    if (!prior) return;
    if (prior.kind === "text") {
      setNotes((current) => ({ ...current, [id]: prior.text }));
      return;
    }
    setPicked((current) => ({ ...current, [id]: prior.choiceIds }));
  }

  useEffect(() => {
    const waiting =
      job?.phase === "awaiting_answers" || stage === "matched" || stage === "awaiting_answers";
    if (!slug || !waiting) {
      setQuestionsLoaded(true);
      return;
    }
    if (job?.phase === "starting" || job?.phase === "running") return;
    let stop = false;
    void (async () => {
      const list = await loadPending();
      if (stop) return;
      keepAnswers(list);
      await loadPriors();
      if (stop) return;
      setQuestionsLoaded(true);
    })();
    return () => {
      stop = true;
    };
  }, [slug, job?.phase, stage]);

  useEffect(() => {
    const approving = job?.phase === "awaiting_approval" || stage === "awaiting_approval";
    if (!slug || !approving || job?.phase === "starting" || job?.phase === "running") return;
    let stop = false;
    void (async () => {
      const response = await fetch("/api/cvt", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ command: "diff", run: slug }),
      });
      const payload = (await response.json()) as {
        envelope?: { data?: { items?: ReviewItem[]; pending?: string[] } };
      };
      if (stop) return;
      const data = payload.envelope?.data;
      const items = Array.isArray(data?.items) ? data.items : [];
      const waiting = Array.isArray(data?.pending) ? data.pending.length : 0;
      setReview({ items, pending: waiting });
      setError((current) => (/pending review/i.test(current) ? "" : current));
    })();
    return () => {
      stop = true;
    };
  }, [slug, job?.phase, stage]);

  const turns = job ? visibleTurns(job) : [];
  const spoken = turns.filter((turn) => turn.role === "user" || (turn.role === "assistant" && turn.text));
  const turnKey = spoken.map((turn) => `${turn.id}:${turn.status || ""}:${(turn.text || "").length}`).join("|");

  useEffect(() => {
    const node = scroller.current;
    if (!node || !stick.current) return;
    node.scrollTop = node.scrollHeight;
  }, [turnKey, questions.length, job?.phase]);

  if (!slug) return null;
  const phase = job?.phase || "";
  const writing = providerStatus(phase === "error" ? job?.message || "" : "", {
    provider,
    cursor: cursorReady,
    anthropic: anthropicReady,
  });
  const visibleMessage = writing.showMessage ? job?.message || "" : "";
  const running = phase === "starting" || phase === "running";
  const asking = questions.length > 0 && !running;
  const approving = !running && (phase === "awaiting_approval" || stage === "awaiting_approval");
  const assistantSaid = spoken.some((turn) => turn.role === "assistant" && turn.text);
  const questionStage = stage === "matched" || stage === "awaiting_answers" || phase === "awaiting_answers";
  const showContinue =
    connected === true && !running && !asking && !approving && phase !== "finished" && (!questionStage || questionsLoaded);
  const startedAt = job?.updatedAt ? Date.parse(job.updatedAt) : now;
  const elapsed = elapsedLabel(now - (Number.isFinite(startedAt) ? startedAt : now));
  const waitSteps = mode === "polish" ? [] : progress?.steps && progress.steps.length > 0 ? progress.steps : [...STEP_LABELS];
  const waitTitle = mode === "polish" ? "Polishing this CV" : progress?.title || "Tailoring this CV";
  const waitDetailText =
    mode === "polish" ? "Fitting the pages. This usually takes a few minutes." : progress?.detail || "This usually takes a few minutes.";
  const heading = liveLabel || title;

  async function resume(kind: "answers" | "approved" | "message", text = "") {
    setPending(true);
    setError("");
    seenPhase.current = "";
    const response = await fetch("/api/infer", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        command: kind === "message" ? "message" : "run",
        run: slug,
        mode: job?.mode === "reply" || job?.mode === "tailor" || job?.mode === "polish" ? job.mode : mode,
        resume: kind === "message" ? undefined : kind,
        text,
      }),
    });
    const payload = (await response.json()) as { error?: string; status?: InferStatus };
    setPending(false);
    if (!response.ok) {
      setError(payload.error || "The run did not continue.");
      return;
    }
    if (payload.status) setJob(payload.status);
    if (kind === "message") setDraft("");
  }

  async function applyAnswers() {
    setPending(true);
    setError("");
    const fresh = await loadPending();
    keepAnswers(fresh);
    if (fresh.length === 0) {
      await resume("answers");
      return;
    }
    const plan = pendingReply(fresh, picked, notes);
    if (plan.auto || plan.select.length > 0) {
      const response = await fetch("/api/cvt", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          command: "answers-apply",
          run: slug,
          mode: "commit",
          auto: plan.auto,
          select: plan.select,
          defaultRest: plan.defaultRest,
        }),
      });
      const payload = (await response.json()) as {
        error?: string;
        envelope?: { ok?: boolean; exit_code?: number; error?: { message?: string; hint?: string } };
      };
      const failure =
        !response.ok || payload.envelope?.ok === false
          ? applyFailure(payload.envelope, payload.error, {
              questions: fresh,
              notes,
              rawText: pendingReply(fresh, picked, notes).prose,
            })
          : "";
      if (failure) {
        setPending(false);
        setError(failure);
        return;
      }
    }
    if (plan.prose) await resume("message", plan.prose);
    else await resume("answers");
  }

  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-border-button-default bg-background-primary-default p-4">
      {heading || headerAction ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          {heading ? <h2 className="min-w-0 flex-1 text-headline-medium text-text-primary">{heading}</h2> : null}
          {headerAction}
        </div>
      ) : null}
      {running ? (
        <WaitCard
          title={waitTitle}
          detail={waitDetailText}
          steps={waitSteps}
          step={typeof progress?.step === "number" ? progress.step : 0}
          elapsed={elapsed}
        />
      ) : null}
      {connected === false ? (
        <div className="flex flex-col gap-2">
          <p className="text-body-regular text-text-primary">
            Connect Cursor to continue. The editor login is separate.
          </p>
          {loginUrl ? (
            <a className="text-body-regular text-text-primary underline" href={loginUrl}>
              Open the Cursor login
            </a>
          ) : null}
          <div>
            <Button disabled={pendingContinue || connected === null} onClick={onConnect}>
              Connect Cursor
            </Button>
          </div>
        </div>
      ) : null}
      {showContinue ? (
        <div className="flex flex-col gap-3">
          {detail ? <p className="text-body-regular text-text-secondary">{detail}</p> : null}
          <div className="flex flex-wrap items-center gap-3">
            <ProviderSelect value={provider} onChange={onProvider} disabled={pending || pendingContinue} />
            <Button variant="secondary" disabled={pending || pendingContinue || !writing.canContinue} onClick={onContinue}>
              Continue
            </Button>
          </div>
          {writing.text ? <p className="text-body-regular text-text-secondary">{writing.text}</p> : null}
        </div>
      ) : null}
      {asking ? null : spoken.length > 0 || (!running && visibleMessage && !approving) ? (
      <div className="relative min-h-0">
        <div
          ref={scroller}
          role="log"
          aria-label="Conversation"
          aria-live="polite"
          className="flex max-h-96 flex-col gap-3 overflow-y-auto pe-1"
          onScroll={(event) => {
            fade.onScroll(event);
            const node = event.currentTarget;
            stick.current = node.scrollHeight - node.scrollTop - node.clientHeight < 48;
          }}
        >
          {!running && !assistantSaid && visibleMessage ? (
            <p
              className={
                phase === "error"
                  ? "whitespace-pre-wrap text-body-regular text-text-error-primary"
                  : "text-body-regular text-text-primary"
              }
            >
              {visibleMessage}
            </p>
          ) : null}
          {spoken.map((turn, index) => {
            if (turn.role === "user") {
              return (
                <div key={`${turn.id}-${index}`} className="flex justify-end">
                  <p className="max-w-[36rem] rounded-2xl bg-background-secondary-default px-3 py-2 text-body-regular text-text-primary">
                    {turn.text}
                  </p>
                </div>
              );
            }
            if (turn.role === "tool") return null;
            if (turn.role === "assistant" && turn.text) {
              return <MarkdownBlock key={`${turn.id}-${index}`} markdown={turn.text} />;
            }
            return null;
          })}
          {phase === "error" && assistantSaid ? (
            <p className="whitespace-pre-wrap text-body-regular text-text-error-primary">{job?.message}</p>
          ) : null}
        </div>
        <ScrollFade progress={fade.progress} surfaceClassName="from-background-primary-default" />
      </div>
      ) : null}

      {asking ? (
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            void applyAnswers();
          }}
        >
          <QuestionFields
            questions={questions}
            picked={picked}
            notes={notes}
            priors={priors}
            onUsePrior={usePrior}
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
          <div>
            <Button type="submit" disabled={pending || running}>
              Apply answers and continue
            </Button>
          </div>
        </form>
      ) : null}

      {approving ? (
        <div className="flex flex-col gap-3 border-t border-separator-border pt-4">
          <p className="text-body-regular text-text-primary">
            {review && review.pending > 0
              ? `${review.pending} changes are in this draft. Approving accepts the wording and renders the PDF.`
              : "Approving accepts the wording and renders the PDF."}{" "}
            You pick modern, classic, or sidebar on the next screen. To change the wording, write it below.
          </p>
          <div>
            <Button
              disabled={pending || running}
              onClick={async () => {
                setPending(true);
                setError("");
                const response = await fetch("/api/cvt", {
                  method: "POST",
                  headers: { "content-type": "application/json" },
                  body: JSON.stringify({ command: "approve", run: slug, all: true }),
                });
                const payload = (await response.json()) as { error?: string; envelope?: { ok?: boolean; error?: { message?: string } } };
                if (!response.ok || payload.envelope?.ok === false) {
                  setPending(false);
                  setError(payload.envelope?.error?.message || payload.error || "Approval did not stick.");
                  return;
                }
                await resume("approved");
              }}
            >
              Approve and render
            </Button>
          </div>
          {review && review.items.length > 0 ? (
            <ul className="flex max-h-80 flex-col gap-3 overflow-y-auto">
              {review.items.map((item) => {
                const after = String(item.after || "").trim();
                const before = String(item.before || "").trim();
                const removed = item.kind === "dropped";
                const text = removed ? before : after || before;
                if (!text) return null;
                return (
                  <li key={`${item.id}-${item.kind || ""}`} className="text-body-regular text-text-primary">
                    {item.section ? <span className="text-body-2-medium text-text-secondary">{item.section}. </span> : null}
                    {removed ? <span className="text-text-secondary">Removed. </span> : null}
                    {text}
                    {!removed && before && before !== after ? (
                      <span className="mt-1 block text-body-2-regular text-text-tertiary">Was: {before}</span>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          ) : null}
        </div>
      ) : null}

      {showContinue || running ? null : (
        <div className="flex justify-end">
          <ProviderSelect value={provider} onChange={onProvider} disabled={pending || running} />
        </div>
      )}
      {(showContinue && spoken.length === 0) || running ? null : (
      <form
        className="flex items-end gap-2 border-t border-separator-border pt-3"
        onSubmit={(event) => {
          event.preventDefault();
          const text = draft.trim();
          if (!text || pending || running) return;
          void resume("message", text);
        }}
      >
        <div className="min-w-0 flex-1">
          <Textarea
            aria-label="Message"
            placeholder={
              asking
                ? "Or reply in your own words"
                : approving
                  ? "Ask for a change before approving"
                  : "Message"
            }
            rows={1}
            autoResize
            maxRows={6}
            value={draft}
            isDisabled={pending || running}
            onChange={setDraft}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                const text = draft.trim();
                if (!text || pending || running) return;
                void resume("message", text);
              }
            }}
          />
        </div>
        <Button type="submit" disabled={pending || running || draft.trim() === ""}>
          Send
        </Button>
      </form>
      )}
      {error ? (
        <p className="whitespace-pre-wrap text-body-regular text-text-error-primary">{error}</p>
      ) : null}
    </section>
  );
}
