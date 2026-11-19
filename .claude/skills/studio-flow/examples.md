# Studio flow examples

Props live on `web/src/components/studio/tool-flow.tsx`. Toolbox (`web/src/components/studio/toolbox-form.tsx`) is the reference page.

## Toolbox

```tsx
const tools = [
  { id: "tailor", title: "Tailor to a job", summary: "Match one posting. The facts stay yours.", icon: RiFileEditLine },
  { id: "polish", title: "Polish a CV", summary: "Keep every fact. No job to match.", icon: RiSparkling2Line },
];

<ToolPicker tools={tools} selectedId={tool} onSelect={setTool} />
<Composer
  title={selected.title}
  provider={provider}
  onProvider={saveProvider}
  submitLabel={tool === "polish" ? "Polish this CV" : "Start tailoring"}
  canSubmit={ready}
  hint={blocker}
  onSubmit={tool === "polish" ? startPolish : startTailor}
>
  <DocumentSource
    legend="CV"
    modes={[
      { id: "library", label: "Your files" },
      { id: "upload", label: "Upload" },
    ]}
    mode={cvMode}
    uploadLabel="Upload a CV"
    // library, paste, and onFile: see toolbox-form.tsx
  />
  {tool === "tailor" ? (
    <DocumentSource
      legend="Job description"
      modes={[
        { id: "paste", label: "Paste text" },
        { id: "library", label: "Saved" },
        { id: "upload", label: "Upload" },
      ]}
      mode={jdMode} // defaultSourceMode returns "paste"
      pasteLabel="Paste the job"
      uploadLabel="Upload a job description"
    />
  ) : null}
</Composer>
```

Open on the first tool. Switching tools keeps the CV the person already picked. The job field exists only on tools that need one.

## A later page

A cover-letter page, or any new Studio surface, imports the same three components. It does not copy the toolbox form.

```tsx
<ToolPicker tools={letterTools} selectedId={tool} onSelect={setTool} />
<Composer title={selected.title} provider={provider} onProvider={saveProvider} submitLabel="Draft the letter" canSubmit={ready} onSubmit={draft}>
  <DocumentSource legend="CV" modes={cvModes} mode={cvMode} uploadLabel="Upload a CV" /* ... */ />
  <DocumentSource legend="Job description" modes={jdModes} mode={jdMode} pasteLabel="Paste the job" /* ... */ />
</Composer>
```

Add a tool by appending to `letterTools` and branching `onSubmit`. The picker grid already wraps.
