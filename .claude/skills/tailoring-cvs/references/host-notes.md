# Host notes

How the same skill behaves on each host. The scripts never depend on host substitutions: commands always run from
the repo root as `uv run .claude/skills/tailoring-cvs/scripts/cvt.py <command>`.

## Contents

- [Cursor](#cursor)
- [Claude Code](#claude-code)
- [Claude API container](#claude-api-container)
- [claude.ai](#claudeai)
- [Personal data](#personal-data)

## Cursor

- Skills load from `.claude/skills/` (compatibility path); the folder name must equal `name`. The core skill is
  model-invocable; the five wrappers (`/tailor-cv`, `/cv-continue`, `/cv-status`, `/cv-render`, `/cv-profile`)
  appear only under `/`.
- A skill invoked with `/name` is attached to that one message. For a whole session use Custom Mode (Option+Enter
  on the skill). Otherwise a later reply still re-triggers the core skill by its description; start with `cvt status`.
- Question tool: `cvt questions RUN --format host --host cursor` prints
  `{"title": "...", "questions": [{"id": "q-1", "prompt": "...", "options": [{"id": "...", "label": "..."}],
  "allow_multiple": true}]}`. Pass it to the ask-questions tool (it always offers free text), then map the picked
  option ids to `answers-apply --select q-N=ID`. If no tool is available use `--format chat`.
- Sandbox: if `uv` cannot write its cache, prefix commands with `UV_CACHE_DIR=.cache/uv`. Typst's Python wheel is the
  primary renderer, so a missing `typst` CLI is fine.
- Subagent: `.cursor/agents/cv-critic.md` (`model: claude-opus-5-5[effort=high]`, `readonly: true`). `.cursor/`
  takes precedence over `.claude/` when names clash.

## Claude Code

- Skills and subagents load from `.claude/skills/` and `.claude/agents/`. Wrappers use `argument-hint`,
  `disable-model-invocation`, and `allowed-tools: Bash(uv run *)`. When a body has no placeholder, Claude Code
  appends `ARGUMENTS: <text>`; wrapper bodies say "the text after this command", which works everywhere.
- Question tool: `cvt questions RUN --format host --host claude_code` prints
  `{"calls": [[{"question": "...", "header": "<=12 chars", "multiSelect": true, "options": [{"label": "...",
  "description": "..."}]}]]}`. Use `AskUserQuestion` with at most 4 questions per call and at most 4 options per
  question (longer lists are already split into parts). Free text arrives through "Other". A timed-out dialog counts
  as skip, so the default applies.
- Subagent: `.claude/agents/cv-critic.md` (`model: opus`, `tools: Read, Glob, Grep`).
- The skill listing truncates description plus `when_to_use` at 1,536 characters; lint enforces it.

## Claude API container

No network and no package installs. Use `python3` instead of `uv`:
`python3 .claude/skills/tailoring-cvs/scripts/cvt.py <command>` with `jsonschema`, `pypdf`, and `typst` preinstalled
if the container has them. Without Typst, `cvt render` writes `build/cv.typ` and `cv.md`, then exits 3. Tell the user
to compile locally: `typst compile build/cv.typ cv.pdf` with `<skill>/assets/fonts` as Typst's font path, or paste
`cv.md` into their editor. There is no persistence between sessions, so re-attach the run files to resume.

## claude.ai

Run `cvt package-skill --out dist/` locally and upload `dist/tailoring-cvs.zip` under Settings, Capabilities, Skills.
The zip holds only the core skill (no `out/`, `profiles/`, or CVs). claude.ai and the Skills API accept only the
frontmatter keys `name`, `description`, `license`, `compatibility`, `metadata`, and `allowed-tools`; the core skill
uses the first five. Checkpoints use the chat format, and nothing persists between conversations.

## Personal data

CVs, JDs, `out/`, `profiles/`, and `.cache/` are git-ignored and stay on the user's machine. The skill zip contains no
personal data. Skills API and claude.ai uploads are not covered by zero data retention, and CVs sent in
conversations are processed by the host the user chose. Never paste CV contents into files that are committed.
