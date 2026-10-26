---
name: cv-profile
description: Lists, shows, revokes, or re-activates the confirmed experience facts (attestations) and cached profile stored for a person in profiles/.
argument-hint: "[list | show att-NNN | revoke att-NNN | activate att-NNN] [--person slug]"
disable-model-invocation: true
allowed-tools: Bash(uv run *)
---
Read `.claude/skills/tailoring-cvs/SKILL.md`, then run the matching `cvt attest` or `cvt profile-show` command for
the text after this command. Before revoking anything, show the attestation and ask the user to confirm. Explain
that revoked facts will no longer be used and that runs which cite them must be re-tailored.
