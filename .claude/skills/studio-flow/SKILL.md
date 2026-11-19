---
name: studio-flow
description: >-
  Builds gtjob Studio pages with the shared BoardUI tool flow: a card picker,
  Cursor as the default model, and one document source at a time (paste, saved
  files, or upload). Use when adding or changing Toolbox, a tool, a CV or job
  description input, a model provider control, or any Studio page that starts
  from a document.
---

# Studio flow

Compose tool pages from `web/src/components/studio/tool-flow.tsx`. Do not invent a second layout. BoardUI rules in `web/.cursor/rules/boardui.mdc` still apply: semantic tokens, composite type, installed components.

The shape comes from Gamma's create screen: pick a format as a card, then one composer. Other ways to supply the same input are modes of that composer, not extra fields stacked underneath. The model sits in the header. The action sits at the end and names the outcome.

## Order on the page

1. Page title and one sentence.
2. `ToolPicker`. One tool selected. Cards wrap, so more tools do not need a new page.
3. `Composer` for the selected tool only. It already places `ProviderSelect` in the header. Cursor is the default (`readProvider` returns `cursor` when nothing is saved). Automatic and Anthropic stay in the menu.
4. One `DocumentSource` per input. Only the active mode is visible.
5. The result (progress, preview, download) stays below the composer.

## Document modes

`defaultSourceMode` is the policy:

- A mode list that includes `paste` opens on paste. Job descriptions do this.
- A file list opens on `library` when it has files, otherwise `upload`. CVs do this.

Hide the switch when a document has one mode. Name the modes for the object: CV uses "Your files" and "Upload"; a job uses "Paste text", "Saved", and "Upload".

A real upload starts when the file is chosen. Do not wait on `FileUpload`'s simulated progress. `DocumentSource` already matches that drop zone and calls `onFile` immediately.

## Accessible names

Keep these stable. `web/e2e/studio.ts` finds the toolbox by them:

| Control | Name |
|---|---|
| Tool card | the tool title, e.g. `Tailor to a job` |
| CV file input | `Upload a CV` |
| Job textarea | `Paste the job` |
| Reply checkbox | `Write a reply` |
| Tailor submit | `Start tailoring` |

`uploadLabel` and `pasteLabel` are those names. A new tool picks the same pattern: `Upload a {thing}`, `Paste the {thing}`, and a submit label that says what will happen.

## Adding a tool

Add a `ToolChoice` (id, title, one-line summary, Remix icon). Branch the composer's children and `onSubmit` for that id. The submit handler stays in the page: each tool calls its own command. Do not fork `tool-flow.tsx` for one tool.

See [examples.md](examples.md) for the toolbox and for a later page that reuses the same components.

## Leave alone

- Do not put the model control above the tool cards, or repeat it inside each document.
- Do not show a file select, an upload field, and a textarea at the same time.
- Do not change `readProvider`'s missing-file default away from Cursor unless the user asks.
- Offline replay (`GTJOB_FAKE_LLM`) does not need a Cursor login. The infer route already allows that.
