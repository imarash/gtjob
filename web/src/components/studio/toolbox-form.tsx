"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button, ButtonLink } from "@/components/base/buttons/button";
import { Select, SelectItem } from "@/components/base/select/select";
import { Textarea } from "@/components/base/textarea/textarea";
import { CursorConnect, InferPanel } from "@/components/studio/infer-panel";
import { PillTab, PillTabList } from "@/components/base/tabs/pill-tab";
import { describeStage } from "@/lib/stage-copy.mjs";

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
  if (run.kind === "polish" && run.title && run.title !== run.slug) return run.title;
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
  const [cv, setCv] = useState(cvs[0] ?? "");
  const [polishCv, setPolishCv] = useState(cvs[0] ?? "");
  const [jd, setJd] = useState(jds[0] ?? "");
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
  const [loginUrl, setLoginUrl] = useState("");

  const scoped = runs.filter((run) => (tool === "polish" ? run.kind === "polish" : run.kind !== "polish"));
  const pinned = scoped.find((run) => run.slug === activeSlug);
  const working = pinned && !pinned.preview ? pinned : pinned ? undefined : scoped.find((run) => !run.preview);
  const finished = pinned?.preview ? pinned : scoped.find((run) => run.preview && run.slug !== working?.slug);
  const earlier = scoped.filter((run) => run.preview && run.slug !== finished?.slug);

  useEffect(() => {
    let stop = false;
    async function tick() {
      const response = await fetch("/api/infer");
      const payload = (await response.json()) as { connected?: boolean; login?: { url?: string } };
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
      setError(payload.error || "Cursor did not start.");
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
      setPolishCv(payload.name);
    } else setJd(payload.name);
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

  function selectTool(next: "tailor" | "polish") {
    setTool(next);
    setError("");
    setNotice("");
    setLayout("");
  }

  async function startPolish(event: { preventDefault: () => void }) {
    event.preventDefault();
    setPending(true);
    setError("");
    setNotice("");
    const response = await fetch("/api/cvt", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ command: "polish-start", cv: polishCv }),
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

  return (
    <div className="flex flex-col gap-8">
      <PillTabList aria-label="CV tools">
        <PillTab variant="gray" isSelected={tool === "tailor"} onSelect={() => selectTool("tailor")}>
          Tailor to a job
        </PillTab>
        <PillTab variant="gray" isSelected={tool === "polish"} onSelect={() => selectTool("polish")}>
          Polish a CV
        </PillTab>
      </PillTabList>
      {tool === "tailor" ? (
      <form
        className="flex flex-col gap-4 rounded-2xl border border-border-button-default p-4"
        onSubmit={async (event) => {
          event.preventDefault();
          setPending(true);
          setError("");
          setNotice("");
          const response = await fetch("/api/cvt", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              command: "init",
              cv,
              jd: jdText.trim() ? "" : jd,
              jdText: jdText.trim(),
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
        }}
      >
        <div className="grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-2">
            {cvs.length === 0 ? (
              <p className="text-body-regular text-text-secondary">No CV in CVs/ yet. Upload one.</p>
            ) : (
              <Select aria-label="CV" selectedKey={cv} onSelectionChange={(key) => typeof key === "string" && setCv(key)}>
                {cvs.map((name) => (
                  <SelectItem key={name} id={name}>
                    {name}
                  </SelectItem>
                ))}
              </Select>
            )}
            <label className="text-body-2-regular text-text-secondary">
              Upload a CV
              <input
                className="mt-1 block text-body-regular text-text-primary"
                type="file"
                accept=".pdf,.md,.txt"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void upload("cv", file);
                }}
              />
            </label>
          </div>
          <div className="flex flex-col gap-2">
            {jds.length > 0 ? (
              <Select
                aria-label="Job description file"
                selectedKey={jd}
                onSelectionChange={(key) => typeof key === "string" && setJd(key)}
              >
                {jds.map((name) => (
                  <SelectItem key={name} id={name}>
                    {name}
                  </SelectItem>
                ))}
              </Select>
            ) : null}
            <label className="text-body-2-regular text-text-secondary">
              Upload a job description
              <input
                className="mt-1 block text-body-regular text-text-primary"
                type="file"
                accept=".pdf,.md,.txt"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void upload("jd", file);
                }}
              />
            </label>
          </div>
        </div>
        <Textarea aria-label="Job text" label="Or paste the job" value={jdText} onChange={setJdText} rows={4} />
        <div className="flex flex-wrap items-end gap-3">
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
          <label className="flex items-center gap-2 text-body-regular text-text-primary">
            <input type="checkbox" checked={withReply} onChange={(event) => setWithReply(event.target.checked)} />
            Write a reply
          </label>
          <Button type="submit" disabled={pending || !cv || (!jd && jdText.trim() === "")}>
            {pending ? "Working" : "Start tailoring"}
          </Button>
        </div>
        <p className="text-body-2-regular text-text-secondary">
          The layout above is the one this draft is fitted to. After the PDF is ready you can compare modern, classic, and sidebar, then download the one you want.
        </p>
      </form>
      ) : (
      <form
        className="flex flex-col gap-4 rounded-2xl border border-border-button-default p-4"
        onSubmit={(event) => void startPolish(event)}
      >
        <p className="text-body-regular text-text-secondary">
          Every fact stays. There is no job to match, so the CV is about two or three pages, in modern, classic, and sidebar.
        </p>
        {cvs.length === 0 ? (
          <p className="text-body-regular text-text-secondary">No CV in CVs/ yet. Upload one.</p>
        ) : (
          <Select
            aria-label="CV to polish"
            selectedKey={polishCv}
            onSelectionChange={(key) => typeof key === "string" && setPolishCv(key)}
          >
            {cvs.map((name) => (
              <SelectItem key={name} id={name}>
                {name}
              </SelectItem>
            ))}
          </Select>
        )}
        <label className="text-body-2-regular text-text-secondary">
          Upload a CV
          <input
            className="mt-1 block text-body-regular text-text-primary"
            type="file"
            accept=".pdf,.md,.txt"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void upload("cv", file);
            }}
          />
        </label>
        <div>
          <Button type="submit" disabled={pending || !polishCv}>
            {pending ? "Working" : "Polish this CV"}
          </Button>
        </div>
      </form>
      )}
      {notice ? <p className="text-body-regular text-text-primary">{notice}</p> : null}
      {error ? <p className="text-body-regular text-text-error-primary">{error}</p> : null}

      {working ? (
        <InferPanel
          key={working.slug}
          slug={working.slug}
          title={runTitle(working)}
          stage={working.stage}
          mode={working.kind === "polish" ? "polish" : withReply ? "reply" : "tailor"}
          connected={connected}
          loginUrl={loginUrl}
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
          <h2 className="text-headline-medium text-text-primary">{runTitle(finished)}</h2>
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

      {earlier.length > 0 ? (
        <details className="rounded-2xl border border-border-button-default px-4 py-3">
          <summary className="cursor-pointer text-body-medium text-text-primary">Earlier CVs</summary>
          <ul className="mt-3 flex flex-col gap-2">
            {earlier.map((run) => (
              <li key={run.slug}>
                <a className="text-body-regular text-text-secondary underline" href={`/runs/${run.slug}`}>
                  {run.title}
                </a>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
