"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { RiFileEditLine, RiSparkling2Line } from "@remixicon/react";
import { Button, ButtonLink } from "@/components/base/buttons/button";
import { Checkbox } from "@/components/base/checkbox/checkbox";
import { Select, SelectItem } from "@/components/base/select/select";
import { CursorConnect, InferPanel } from "@/components/studio/infer-panel";
import {
  Composer,
  DocumentSource,
  ToolPicker,
  defaultSourceMode,
  type SourceMode,
  type ToolChoice,
} from "@/components/studio/tool-flow";
import { providerStatus } from "@/lib/provider-hint.mjs";
import { describeStage } from "@/lib/stage-copy.mjs";

const ACCEPT = ".pdf,.md,.txt";

const CV_MODES = [
  { id: "library" as const, label: "Your files" },
  { id: "upload" as const, label: "Upload" },
];

const JD_MODES = [
  { id: "paste" as const, label: "Paste text" },
  { id: "library" as const, label: "Saved" },
  { id: "upload" as const, label: "Upload" },
];

const TOOLS: ToolChoice[] = [
  {
    id: "tailor",
    title: "Tailor to a job",
    summary: "Match one posting. The facts stay yours.",
    icon: RiFileEditLine,
  },
  {
    id: "polish",
    title: "Polish a CV",
    summary: "Keep every fact. No job to match.",
    icon: RiSparkling2Line,
  },
];

type Download = { file: string; label: string };

const LAYOUTS = ["modern", "classic", "sidebar"] as const;

const LAYOUT_LABEL: Record<(typeof LAYOUTS)[number], string> = {
  modern: "Modern",
  classic: "Classic",
  sidebar: "Sidebar",
};

export type ToolboxRun = {
  slug: string;
  title: string;
  stage: string;
  template: string;
  downloads: Download[];
  preview: string;
  hasReport: boolean;
  reply: string;
  kind: "tailor" | "polish";
};

function jobLabel(slug: string) {
  return slug.replace(/^\d{8}-/, "").replace(/-/g, " ");
}

function layoutPdf(run: ToolboxRun, name: string) {
  const preview = `preview-${name}.pdf`;
  const found = run.downloads.find((item) => item.file === preview || item.file.toLowerCase().endsWith(`-${name}.pdf`));
  return found?.file || "";
}

function runTitle(run: ToolboxRun) {
  if (run.title && run.title !== run.slug) return run.title;
  return jobLabel(run.slug);
}

function fileHref(slug: string, file: string, download = false) {
  const href = `/runs/${slug}/pdf?file=${encodeURIComponent(file)}`;
  return download ? `${href}&download=1` : href;
}

export function ToolboxForm({
  cvs,
  jds,
  runs,
}: {
  cvs: string[];
  jds: string[];
  runs: ToolboxRun[];
}) {
  const router = useRouter();
  const [tool, setTool] = useState<"tailor" | "polish">("tailor");
  const [cvMode, setCvMode] = useState<SourceMode>(defaultSourceMode(CV_MODES, cvs.length));
  const [jdMode, setJdMode] = useState<SourceMode>(defaultSourceMode(JD_MODES, jds.length));
  const [cv, setCv] = useState(cvs[0] ?? "");
  const [jd, setJd] = useState(jds[0] ?? "");
  const [uploadedCv, setUploadedCv] = useState("");
  const [uploadedJd, setUploadedJd] = useState("");
  const [jdText, setJdText] = useState("");
  const [template, setTemplate] = useState("modern");
  const [withReply, setWithReply] = useState(true);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [renderingLayouts, setRenderingLayouts] = useState(false);
  const [layout, setLayout] = useState("");
  const [layoutPages, setLayoutPages] = useState<Record<string, number>>({});
  const [activeSlug, setActiveSlug] = useState("");
  const [connected, setConnected] = useState<boolean | null>(null);
  const [cursorReady, setCursorReady] = useState<boolean | null>(null);
  const [anthropicReady, setAnthropicReady] = useState(false);
  const [provider, setProvider] = useState("cursor");
  const [loginUrl, setLoginUrl] = useState("");
  const cvFiles = uploadedCv && !cvs.includes(uploadedCv) ? [uploadedCv, ...cvs] : cvs;
  const jdFiles = uploadedJd && !jds.includes(uploadedJd) ? [uploadedJd, ...jds] : jds;
  const chosenCv = cvMode === "upload" ? uploadedCv : cv;
  const chosenJd = jdMode === "library" ? jd : jdMode === "upload" ? uploadedJd : "";

  const scoped = runs.filter((run) => (tool === "polish" ? run.kind === "polish" : run.kind !== "polish"));
  // A visit starts on the form. A previous run is shown only after this session starts it or opens it.
  const pinned = scoped.find((run) => run.slug === activeSlug);
  const working = pinned && !pinned.preview ? pinned : undefined;
  const finished = pinned?.preview ? pinned : undefined;
  const openRuns = scoped.filter((run) => !run.preview);
  const finishedRuns = scoped.filter((run) => run.preview);
  const writingChoice = providerStatus("", {
    provider,
    cursor: cursorReady === true,
    anthropic: anthropicReady,
  });

  useEffect(() => {
    let stop = false;
    async function tick() {
      const response = await fetch("/api/infer");
      const payload = (await response.json()) as {
        connected?: boolean;
        cursor?: boolean;
        anthropic?: boolean;
        provider?: string;
        login?: { url?: string };
      };
      if (stop) return;
      setConnected(Boolean(payload.connected));
      setCursorReady(Boolean(payload.cursor));
      setAnthropicReady(Boolean(payload.anthropic));
      if (payload.provider === "auto" || payload.provider === "cursor" || payload.provider === "anthropic") {
        setProvider(payload.provider);
      }
      setLoginUrl(payload.login?.url || "");
    }
    void tick();
    const timer = setInterval(() => void tick(), 3000);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, []);

  async function chooseProvider(next: string) {
    setProvider(next);
    const response = await fetch("/api/infer", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ command: "provider", provider: next }),
    });
    if (!response.ok) setError("The provider was not saved.");
  }

  async function connectCursor() {
    setPending(true);
    await fetch("/api/infer", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ command: "login" }),
    });
    setPending(false);
  }

  async function beginTailoring(slug: string, kind: "tailor" | "polish" = "tailor") {
    setActiveSlug(slug);
    setError("");
    setNotice("");
    const ready = await fetch("/api/infer");
    const auth = (await ready.json()) as { connected?: boolean };
    if (!auth.connected) {
      setConnected(false);
      router.refresh();
      return;
    }
    const response = await fetch("/api/infer", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        command: "run",
        run: slug,
        mode: kind === "polish" ? "polish" : withReply ? "reply" : "tailor",
      }),
    });
    const payload = (await response.json()) as { error?: string; connected?: boolean };
    if (response.status === 409 || payload.connected === false) {
      setConnected(false);
      router.refresh();
      return;
    }
    if (!response.ok) {
      setError(payload.error || "The run did not start.");
      return;
    }
    router.refresh();
  }

  async function upload(kind: "cv" | "jd", file: File) {
    setPending(true);
    setError("");
    const body = new FormData();
    body.set("kind", kind);
    body.set("file", file);
    const response = await fetch("/api/uploads", { method: "POST", body });
    const payload = (await response.json()) as { name?: string; error?: string };
    setPending(false);
    if (!response.ok || !payload.name) {
      setError(payload.error || "Upload failed.");
      return;
    }
    if (kind === "cv") {
      setCv(payload.name);
      setUploadedCv(payload.name);
    } else {
      setJd(payload.name);
      setUploadedJd(payload.name);
    }
    router.refresh();
  }

  async function advance(slug: string) {
    setPending(true);
    setError("");
    const response = await fetch("/api/cvt", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ command: "advance", run: slug }),
    });
    const payload = (await response.json()) as { message?: string; error?: string; stage?: string; blocked?: string };
    setPending(false);
    if (!response.ok) {
      setError(payload.error || "That step did not run.");
      return;
    }
    if (payload.stage === "reported" || payload.stage === "validated" || payload.blocked === "ready") {
      setActiveSlug(slug);
      router.refresh();
      return;
    }
    await beginTailoring(slug);
  }

  const reply = finished?.reply || "";
  const activeLayout = layout || finished?.template || "modern";

  useEffect(() => {
    setLayout("");
    setLayoutPages({});
  }, [finished?.slug]);

  async function chooseLayout(name: string) {
    if (!finished) return;
    const ready = Boolean(layoutPdf(finished, name));
    if (ready || (finished.kind !== "polish" && name === (finished.template || "modern"))) {
      setLayout(name);
      return;
    }
    if (finished.kind === "polish") {
      setError("That layout is not in this polish yet.");
      return;
    }
    setRenderingLayouts(true);
    setError("");
    const response = await fetch("/api/cvt", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ command: "render-templates", run: finished.slug }),
    });
    const payload = (await response.json()) as {
      error?: string;
      templates?: { template: string; pages: number }[];
    };
    setRenderingLayouts(false);
    if (!response.ok) {
      setError(payload.error || "The layouts did not render.");
      return;
    }
    const pages: Record<string, number> = {};
    for (const item of payload.templates || []) pages[item.template] = item.pages;
    setLayoutPages(pages);
    setLayout(name);
    router.refresh();
  }

  function shownFile(run: ToolboxRun) {
    const selected = layout || run.template || "modern";
    return layoutPdf(run, selected) || run.preview;
  }

  function leaveRun() {
    setActiveSlug("");
    setLayout("");
    setNotice("");
    setError("");
  }

  function openRun(slug: string) {
    const match = runs.find((item) => item.slug === slug);
    if (match) setTool(match.kind === "polish" ? "polish" : "tailor");
    setActiveSlug(slug);
    setLayout("");
    setNotice("");
    setError("");
  }

  function selectTool(next: "tailor" | "polish") {
    if (next !== tool) leaveRun();
    setTool(next);
    setError("");
    setNotice("");
  }

  const jdReady = jdMode === "paste" ? jdText.trim().length > 0 : Boolean(chosenJd);
  const cvReady = Boolean(chosenCv);
  const canSubmit = writingChoice.canContinue && cvReady && (tool === "polish" || jdReady);
  const selectedTool = TOOLS.find((item) => item.id === tool) ?? TOOLS[0];

  async function startTailor() {
    setPending(true);
    setError("");
    setNotice("");
    const pasted = jdMode === "paste" ? jdText.trim() : "";
    const response = await fetch("/api/cvt", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        command: "init",
        cv: chosenCv,
        jd: pasted ? "" : chosenJd,
        jdText: pasted,
        template,
      }),
    });
    const payload = (await response.json()) as {
      error?: string;
      envelope?: { ok?: boolean; run?: string; error?: { message?: string } };
      advance?: { message?: string; stage?: string; blocked?: string };
    };
    setPending(false);
    if (!response.ok) {
      setError(payload.error || "The run did not start.");
      return;
    }
    if (!payload.envelope?.ok || !payload.envelope.run) {
      setError(payload.envelope?.error?.message || payload.error || "The run did not start.");
      return;
    }
    const run = payload.envelope.run;
    setActiveSlug(run);
    if (payload.advance?.blocked === "ready") {
      setNotice(payload.advance.message || "The tailored CV is ready.");
    } else {
      await beginTailoring(run);
    }
    router.refresh();
  }

  async function startPolish() {
    setPending(true);
    setError("");
    setNotice("");
    const response = await fetch("/api/cvt", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ command: "polish-start", cv: chosenCv }),
    });
    const payload = (await response.json()) as { error?: string; slug?: string };
    if (!response.ok || !payload.slug) {
      setPending(false);
      setError(payload.error || "The polish did not start.");
      return;
    }
    setTool("polish");
    setActiveSlug(payload.slug);
    setPending(false);
    await beginTailoring(payload.slug, "polish");
    router.refresh();
  }

  const blocker = !writingChoice.canContinue
    ? writingChoice.text
    : !cvReady
      ? "Choose a CV, or upload one."
      : tool === "tailor" && !jdReady
        ? "Paste a job, pick a saved one, or upload a file."
        : "";

  return (
    <div className="flex flex-col gap-8">
      <ToolPicker tools={TOOLS} selectedId={tool} onSelect={(id) => selectTool(id === "polish" ? "polish" : "tailor")} />
      <Composer
        title={selectedTool.title}
        provider={provider}
        onProvider={(next) => void chooseProvider(next)}
        providerDisabled={pending}
        submitLabel={tool === "polish" ? "Polish this CV" : "Start tailoring"}
        pending={pending}
        canSubmit={canSubmit}
        hint={blocker}
        onSubmit={() => void (tool === "polish" ? startPolish() : startTailor())}
        extras={
          tool === "tailor" ? (
            <>
              <div className="w-40">
                <Select
                  aria-label="Template"
                  selectedKey={template}
                  onSelectionChange={(key) => typeof key === "string" && setTemplate(key)}
                >
                  {["modern", "classic", "sidebar"].map((name) => (
                    <SelectItem key={name} id={name}>
                      {name}
                    </SelectItem>
                  ))}
                </Select>
              </div>
              <Checkbox isSelected={withReply} onChange={setWithReply}>
                Write a reply
              </Checkbox>
            </>
          ) : null
        }
      >
        <DocumentSource
          legend="CV"
          modes={CV_MODES}
          mode={cvMode}
          onMode={setCvMode}
          library={cvFiles}
          libraryName={cv}
          onLibrary={setCv}
          libraryLabel="CV"
          emptyLibrary="No CV uploaded yet. Switch to Upload."
          uploadLabel="Upload a CV"
          uploadHint="Drop a CV here, or browse"
          accept={ACCEPT}
          uploadedName={uploadedCv}
          onFile={(file) => void upload("cv", file)}
          pending={pending}
        />
        {tool === "tailor" ? (
          <DocumentSource
            legend="Job description"
            modes={JD_MODES}
            mode={jdMode}
            onMode={setJdMode}
            library={jdFiles}
            libraryName={jd}
            onLibrary={setJd}
            libraryLabel="Saved job description"
            emptyLibrary="No saved job yet. Paste text, or switch to Upload."
            paste={jdText}
            onPaste={setJdText}
            pasteLabel="Paste the job"
            pastePlaceholder="Paste the posting."
            uploadLabel="Upload a job description"
            uploadHint="Drop a job description here, or browse"
            accept={ACCEPT}
            uploadedName={uploadedJd}
            onFile={(file) => void upload("jd", file)}
            pending={pending}
          />
        ) : (
          <p className="text-body-regular text-text-secondary">
            Every fact stays. The CV lands at about two or three pages, in modern, classic, and sidebar.
          </p>
        )}
        {tool === "tailor" ? (
          <p className="text-body-2-regular text-text-secondary">
            This layout is the one the draft is fitted to. After the PDF is ready you can compare modern, classic, and sidebar.
          </p>
        ) : null}
      </Composer>
      {notice ? <p className="text-body-regular text-text-primary">{notice}</p> : null}
      {error ? <p className="text-body-regular text-text-error-primary">{error}</p> : null}
      {cursorReady === false ? (
        <div className="flex flex-col gap-2">
          <p className="text-body-regular text-text-secondary">
            A run uses an Anthropic key when one is set. Connect Cursor to use that account when the key is missing or the quota is used up.
          </p>
          <div>
            <Button type="button" variant="secondary" disabled={pending} onClick={() => void connectCursor()}>
              Connect Cursor
            </Button>
          </div>
        </div>
      ) : null}

      {!pinned && (openRuns.length > 0 || finishedRuns.length > 0) ? (
        <details className="rounded-2xl border border-border-button-default px-4 py-3">
          <summary className="cursor-pointer text-body-medium text-text-primary">Previous work</summary>
          <div className="mt-3 flex flex-col gap-4">
            <p className="text-body-regular text-text-secondary">
              The form above starts a new CV. Open something here when you want to continue it.
            </p>
            {openRuns.length > 0 ? (
              <div className="flex flex-col gap-2">
                <p className="text-body-medium text-text-primary">Still open</p>
                <ul className="flex flex-col gap-2">
                  {openRuns.slice(0, 8).map((run) => (
                    <li key={run.slug} className="flex flex-wrap items-center justify-between gap-3">
                      <span className="min-w-0 text-body-regular text-text-primary">{runTitle(run)}</span>
                      <Button type="button" variant="secondary" onClick={() => openRun(run.slug)}>
                        Continue
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {finishedRuns.length > 0 ? (
              <div className="flex flex-col gap-2">
                <p className="text-body-medium text-text-primary">Finished CVs</p>
                <ul className="flex flex-col gap-2">
                  {finishedRuns.slice(0, 8).map((run) => (
                    <li key={run.slug} className="flex flex-wrap items-center justify-between gap-3">
                      <span className="min-w-0 text-body-regular text-text-primary">{runTitle(run)}</span>
                      <Button type="button" variant="secondary" onClick={() => openRun(run.slug)}>
                        View
                      </Button>
                    </li>
                  ))}
                </ul>
                <a className="text-body-regular text-text-primary underline" href="/runs">
                  All runs
                </a>
              </div>
            ) : null}
          </div>
        </details>
      ) : null}

      {working ? (
        <InferPanel
          key={working.slug}
          slug={working.slug}
          title={runTitle(working)}
          headerAction={
            <Button type="button" variant="secondary" onClick={leaveRun}>
              Start another
            </Button>
          }
          stage={working.stage}
          mode={working.kind === "polish" ? "polish" : withReply ? "reply" : "tailor"}
          connected={connected}
          loginUrl={loginUrl}
          provider={provider}
          cursorReady={cursorReady === true}
          anthropicReady={anthropicReady}
          onProvider={(next) => void chooseProvider(next)}
          detail={
            working.kind === "polish"
              ? "This CV is saved. Continue writes the polished PDF."
              : describeStage(working.stage).detail
          }
          pendingContinue={pending}
          onConnect={() => void connectCursor()}
          onContinue={() => void (working.kind === "polish" ? beginTailoring(working.slug, "polish") : advance(working.slug))}
          onFinished={(slug) => {
            setActiveSlug(slug);
            router.refresh();
          }}
        />
      ) : null}
      {!working ? <CursorConnect /> : null}

      {finished ? (
        <section className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="min-w-0 flex-1 text-headline-medium text-text-primary">{runTitle(finished)}</h2>
            <Button type="button" variant="secondary" onClick={leaveRun}>
              Start another
            </Button>
          </div>
          <div className="flex flex-col gap-2">
            <p className="text-body-regular text-text-secondary">Choose a layout, then download that PDF.</p>
            <div className="flex flex-wrap gap-2">
              {LAYOUTS.map((name) => (
                <Button
                  key={name}
                  type="button"
                  variant={activeLayout === name ? "primary" : "secondary"}
                  disabled={renderingLayouts}
                  onClick={() => void chooseLayout(name)}
                >
                  {LAYOUT_LABEL[name]}
                  {layoutPages[name] ? `, ${layoutPages[name]} pages` : ""}
                </Button>
              ))}
            </div>
            {activeLayout === "sidebar" ? (
              <p className="text-body-2-regular text-text-secondary">
                Sidebar is two columns. Applicant-tracking systems read it less reliably than modern or classic.
              </p>
            ) : null}
            {layoutPdf(finished, "classic") ? null : (
              <p className="text-body-2-regular text-text-secondary">
                Classic and sidebar render the first time you select them. The wording stays the same.
              </p>
            )}
            {renderingLayouts ? <p className="text-body-regular text-text-secondary">Rendering the three layouts.</p> : null}
          </div>
          <div className="grid gap-4 md:grid-cols-[minmax(0,1.35fr)_minmax(16rem,0.85fr)]">
            <iframe
              title={runTitle(finished)}
              src={fileHref(finished.slug, shownFile(finished))}
              className="h-[72vh] w-full rounded-2xl border border-border-button-default bg-background-primary"
            />
            <div className="flex max-h-[72vh] flex-col gap-3 rounded-2xl border border-border-button-default p-4">
              <h3 className="text-body-medium text-text-primary">{finished.kind === "polish" ? "What changed" : "Reply"}</h3>
              {reply ? (
                <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap text-body-2-regular text-text-primary">
                  {reply}
                </pre>
              ) : (
                <p className="text-body-regular text-text-secondary">
                  {finished.kind === "polish"
                    ? "Notes on merged lines and page counts show up here with the PDF."
                    : finished.hasReport
                      ? "The reply is written with the PDF."
                      : "The reply is written once the match report exists."}
                </p>
              )}
              {reply ? (
                <div>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      void navigator.clipboard.writeText(reply);
                      setNotice("Reply copied.");
                    }}
                  >
                    Copy reply
                  </Button>
                </div>
              ) : null}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <ButtonLink href={fileHref(finished.slug, shownFile(finished), true)}>Download PDF</ButtonLink>
            {finished.downloads
              .filter(
                (item) =>
                  item.file !== shownFile(finished) &&
                  !item.file.startsWith("preview-") &&
                  !/-(modern|classic|sidebar)\.pdf$/i.test(item.file),
              )
              .map((item) => (
                <a
                  key={item.file}
                  className="text-body-regular text-text-primary underline"
                  href={fileHref(finished.slug, item.file, true)}
                >
                  {item.label}
                </a>
              ))}
          </div>
        </section>
      ) : null}

    </div>
  );
}
