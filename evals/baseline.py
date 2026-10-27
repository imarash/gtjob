"""No-skill baseline for the judge (WP-23).

The same CV text and job description go to Sonnet with the plain request "Tailor my CV to this job description". There is
no skill, no guide, no truthfulness rule, and no checkpoint. The reply is Markdown and is judged as is.
"""

from __future__ import annotations

from pathlib import Path

from judge import AnthropicJudgeClient  # noqa: F401  (re-exported so callers build one client for both uses)

BASELINE_MODEL = "claude-sonnet-5-5"
BASELINE_MAX_TOKENS = 4000
BASELINE_REQUEST = "Tailor my CV to this job description."
BASELINE_FILE = "baseline.md"


def baseline_prompt(cv_text: str, jd_text: str) -> str:
    return f"{BASELINE_REQUEST}\n\nMy CV:\n\n{cv_text}\n\nJob description:\n\n{jd_text}"


def run_baseline(client, cv_text: str, jd_text: str, *, model: str = BASELINE_MODEL) -> str:
    """Return the baseline CV as Markdown. `client` is any object with `messages_text(model, prompt, max_tokens)`
    or an `AnthropicJudgeClient` (its underlying SDK client is used for a plain text reply)."""
    prompt = baseline_prompt(cv_text, jd_text)
    if hasattr(client, "messages_text"):
        return client.messages_text(model, prompt, BASELINE_MAX_TOKENS).strip()
    resp = client._client.messages.create(  # plain text completion; no system prompt, no schema
        model=model, max_tokens=BASELINE_MAX_TOKENS, messages=[{"role": "user", "content": prompt}])
    return "".join(block.text for block in resp.content if getattr(block, "type", "") == "text").strip()


def save_baseline(results_dir: Path, name: str, markdown: str) -> Path:
    """Keep the baseline text next to the judge results for later inspection."""
    path = results_dir / f"{name}.{BASELINE_FILE}"
    path.write_text(markdown + "\n", encoding="utf-8")
    return path
