# Agentic architecture patterns

Distilled 2026-10-30 from Google Cloud, Azure, Neo4j, and Anthropic. Updated 2026-11-02 from Gulli, *Building AI Agents: From Design Patterns to Production*. Read this file instead of the source pages. Canonical names below are the only names `architect-assess`, `architect-options`, and `architect-plan` may use. Aliases are for recognition, not for new labels.

## What an agentic system is

An agent perceives, plans, acts, observes, and repeats until a goal, a stop condition, or a human gate. A direct model call (summarize, classify, translate, extract in one pass) is not an agent. Retrieval-augmented generation alone is not an agent.

Six parts, name each one when you describe a system:

| Part | Role |
| --- | --- |
| Loop | Decides the next step |
| Runtime | Executes code and uses the filesystem. Includes the harness: code that validates, sandboxes, and verifies what the model proposes. Prompts can be jailbroken; harness rules cannot |
| Tools | Reach external systems. MCP is how agents connect to tools and data. A2A is how agents discover and delegate across stacks. A2UI is declared UI, not injected HTML. AP2 is signed payment mandates |
| Skills | Procedural expertise the loop loads when needed. Two forms: a declarative `SKILL.md` (progressive disclosure), or a programmatic bundle of related tools behind a registry. MCP connects; a skill teaches how to use the connection |
| Memory | Short-term (this session), episodic (what was tried, across sessions), semantic (domain knowledge) |
| Guardrails | Tool scope, validation, identity, human gates, traces. Layer cheap then expensive: pattern check, classifier, agent, output filter |

Orchestration is how work moves between agents. It is code, a model, or both. Say which.

The model proposes. The harness decides whether to execute. Agent = model + harness. If a rule is safety-critical, put it in the harness, not the prompt.

## Selection order

Use the first pattern that fits. Add another only to fix a named failure: tool overload, a security boundary, latency, a quality bar, or cross-domain coordination.

1. **Direct call** — one model pass, no tools, no loop. If the task is a fixed flowchart with no model-dependent branches, stay here and write a script.
2. **Single agent** — one domain, dynamic tool use, path not fully known in advance. Default for a first product. Inner-loop styles of this pattern, not new names: **ReAct** (think, act, observe each step), **Chain-of-Thought** (reason then act), **Plan-and-Execute** (write a plan, then run it). Cap iterations.
3. **Skill on that agent** — the gap is missing expertise, not missing agents. Prefer this before splitting agents. A production skill states what must be known before starting, the shortcuts the agent will try, and the evidence that counts as done. Categories seen in the wild: foundational (docs, sheets), partner (a vendor's product), enterprise (internal process and compliance).
4. **Sequential** — fixed stages. Output of one step is the input of the next. Code picks the next step, not a model.
5. **Parallel** — independent subtasks, or several viewpoints on the same input, then a merge. Cap the fan-out.
6. **Competitive** — several attempts at the same problem; an evaluator picks or merges. Use when diversity matters more than a pipeline. Debate/red-team belongs here or in group chat, not as a new name.
7. **Evaluator loop** — generator, then critic with an explicit rubric, then revise. Cap iterations. Define the fallback when the cap is hit (ship best effort, or escalate). Prefer a verifier the model cannot sweet-talk (tests, a schema, a rubric in code). Compact a failed attempt into a lesson, not a transcript.
8. **Router** — known request types, different tools or policies. A model, a classifier, or embeddings send the request to one specialist. No shared workflow state. Gulli's "handoff" (triage to one specialist) is this pattern.
9. **Handoff** — one active agent. It transfers control when it hits its limit. Cap hops. Compress context before the transfer. This is mid-task transfer, not triage.
10. **Hierarchical** — several domains, one audit trail. A supervisor decomposes, delegates, and synthesizes. Subagents do not need to see each other.
11. **Magentic** — the path cannot be planned up front. A manager keeps a task ledger, revises it, and agents use tools that change external systems. A human can read the ledger before execution.
12. **Network** — peers collaborate with no supervisor. Require an exit condition (iteration cap, time limit, or consensus).
13. **Group chat** — shared thread, debate or maker-checker, often with a human in the thread. Keep it to a few participants. Agents in this pattern usually do not mutate production systems.
14. **Human gate** — pause for approval, correction, or subjective judgment. Persist state at the gate so the run resumes without replaying earlier steps. Gate every mutation that spends money or changes user data.
15. **Custom logic** — the workflow mixes patterns (parallel check, then a branch into two different pipelines). Name the mix. Use this when no single pattern fits, not as a default. A **stateful graph** (nodes, edges, shared state, checkpoints) is how sequential, evaluator loop, and human gate get retries and replay. It is an implementation of this mix, not a 16th pattern.

Hybrids that earn their keep: hierarchical with parallel specialists inside one domain; sequential stages with a router at one branch; a single agent that escalates rare cases to a heavier pattern.

Do not invent canonical names for **daemon / always-on**, **managed platform**, or **harness**. Those answer who runs the loop and what enforces it. Record them under Runtime and Distribution.

## Pattern card

| Name | Also called | Coordination | Use when | Cost of the choice |
| --- | --- | --- | --- | --- |
| Direct call | prompt only | None | One-step language task, or a fixed script | Cheapest. Fails when the path depends on tools or intermediate results |
| Single agent | ReAct loop, CoT, Plan-and-Execute | Model loops: think, act, observe | Open path inside one domain | Latency grows with steps. A bad tool result poisons later steps. Tool count and prompt size degrade tool choice. An uncapped loop is a runaway bill |
| Skill | Agent Skill, SkillRegistry | Same loop, extra files or a tool bundle | Expertise is stable and reusable across hosts | Wrong skill still runs the same loop. Does not create a security boundary. A malicious skill file is prompt injection |
| Sequential | pipeline, prompt chain, routine, crew pipeline | Code, fixed order | Stages depend on each other; audit trail must be linear | Early errors propagate. No parallelism. Rigid |
| Parallel | concurrent, fan-out/fan-in | Code fans out, then merges | Independent work, or multiple lenses, and latency matters | Token and quota spike. Needs a conflict rule. Unsafe if agents share mutable state |
| Competitive | ensemble, voting, debate | Parallel plus a judge | Several answers, pick or merge the best | Same spike as parallel, plus a judge call |
| Evaluator loop | generator-critic, reflection | Loop until rubric or cap | A quality bar you can write down | Each revision adds a full round of calls. A live agent repeating the same failure is futility, not progress |
| Router | coordinator, triage dispatcher, Gulli "handoff" | Model, classifier, or embeddings pick one specialist | Many request types, one should handle it | Extra routing call. Misroutes if types overlap |
| Handoff | transfer, delegation | The active agent transfers | The right specialist appears only mid-task | Bounce loops. Unpredictable path. Noisy context poisons the receiver |
| Hierarchical | supervisor, task decomposition | Supervisor delegates downward | Cross-domain work that must stay auditable | Many model calls. Context must be compacted between levels |
| Magentic | task ledger, adaptive plan | Manager rewrites the plan | Open-ended work, tools change real systems, a human may review the plan | Slow. Stalls on vague goals. Hardest cost to predict |
| Network | swarm, peer-to-peer | Agents message each other | Debate across peers is the point | Highest complexity. May never converge without an exit condition |
| Group chat | council, roundtable | A manager chooses who speaks | Consensus, review, human in the thread | Conversation loops. Weak fit for more than a few agents |
| Human gate | human-in-the-loop, interrupt_before | Pause | High stakes, safety, compliance, subjective approval | The run is synchronous at that step. Needs durable state |
| Custom logic | mixed, stateful graph | Code branches | One workflow truly combines patterns, or needs retry/replay | You own every edge. Harder to debug than a named pattern |

## Requirements that pick the pattern

Ask these of the goal and the repo. They decide the pattern. They are not a questionnaire to paste into the output.

- Is the path known in advance, or open-ended?
- Does the next step depend on the previous result?
- Are the parts independent?
- How many domains, tools, and permission boundaries are there?
- Is latency or quality the scarce resource?
- Must a person approve, or is a trace enough?
- Must an auditor replay why this path was taken?
- Can the model provider be swapped without rewriting the workflow?
- Is the run request-response, a long-running daemon, or a managed platform that owns the loop?
- Must the agent execute generated code, and if so in a sandbox?
- Are generated UI or autonomous payments in scope (A2UI, AP2)?

Control vs shape:

- High control (money, safety, compliance) → direct call, single agent, or sequential.
- Moderate control → router or hierarchical.
- Low control, exploration is the goal → group chat or network.

## Who runs the loop

This is Runtime, not a pattern.

| Shape | Lifetime | Use when | Cost of the choice |
| --- | --- | --- | --- |
| Request-response | One task | A person or API starts each run | Failure is visible to the caller. No watchdog needed |
| Daemon | Until stopped | Work arrives on a timer, a queue, or a folder | Needs a heartbeat, a watchdog that is not the agent, exponential backoff, and a clean shutdown that finishes the current task |
| Managed platform | Until the platform stops it | You want the vendor to own restarts, sandbox compute, and session state | You still own prompts, tools, and policy. You give up loop internals. Evaluate the trade-off only after you know what a homemade daemon costs |

Assign a smaller model to classify, extract, and format. Keep the strongest model for the step that actually needs judgment. When replaceability is required, a fallback chain (primary cloud → secondary cloud → local) is the seam, not a hardcoded SDK.

## Budget bands

Use these bands. Do not invent dollar amounts. Multi-agent runs consume on the order of 10–15× the tokens of a single agent. Concurrent patterns spend that in a spike. Sequential and handoff spend it step by step. Magentic and network are the least predictable.

| Band | Build | Run shape | Typical pattern |
| --- | --- | --- | --- |
| S | Days. One path | ~1× model calls, or one tool loop | Direct call, single agent, or a skill on it |
| M | A few weeks. One product surface | A few calls, or one capped critic loop | Sequential, router, evaluator loop. Managed platform if it owns ops |
| L | Months. Durable state, accounts, or several agents | ~10× tokens, traces, per-role models | Hierarchical, parallel specialists, handoff, daemon with checkpoints |
| XL | A platform: tenancy, billing, versioning, execution for other people's agents | Metered, highly variable | Custom logic over several patterns |

## Production rules

Every option and every plan that introduces an agent follows these.

- Deterministic work stays in code. The model decides only where the path is unknown.
- Each agent gets the tools and data it needs, and no more.
- Validate an agent's output before the next step consumes it. Prefer structured outputs. On failure: retry, ask, or stop.
- Timeouts, retries, and errors that surface. Hidden errors cascade.
- Caps on loops, handoffs, group-chat turns, and spend, plus a defined fallback. Raise when a budget is hit.
- Consecutive tool failures escalate. A live agent repeating the same failure is futility: pause, persist, page a human.
- Concurrent agents do not share mutable state.
- Compact context between agents. Persist the minimum durable state outside the window. Feed forward a lesson from a failed attempt, not the transcript.
- Persist state at a human gate. Checkpoint graph or daemon state so a restart resumes.
- Tool calls that mutate are idempotent. A retry must not duplicate a side effect.
- Agent-generated code runs in a sandbox, never on the host. Writes are path-bounded. Shell uses an allowlist, not a blocklist.
- Scan fetched content (tool results, docs, mail, pages) before it enters context. Indirect injection is the usual attack, not the user's typed jailbreak.
- Trace the decision, the tool call, the handoff, and the intermediate result.
- Test with a rubric or a judge, and grade the trajectory (tools used, recovery, cost), not an exact string match. Red-team cases belong in CI.
- If data is per user, every agent enforces that user's access. A shared store must not leak across users.
- Check input, tool calls, tool results, and the final output.
- Keep the model provider behind one seam when the goal requires replaceability.
- Version prompts and skills. A skill file is code: review it, restrict who can write it, and let the loader — not the model — decide what is loaded.

## Memory

Three lifetimes:

- **Short-term** — this session's messages.
- **Episodic** — what was tried and how it failed, across sessions.
- **Semantic** — domain knowledge. Hybrid search (dense plus keyword) beats dense alone for identifiers and error codes.

A scratchpad holds the plan for a long-horizon run so a crash resumes, not restarts. Decay stale memories or the store becomes noise. Retrieval is a tool the agent calls when it needs it (agentic RAG), not a one-shot retrieve-then-generate pipeline.

Add a knowledge graph only when the goal needs relationships (who owns what, what depends on what) and a trace of how a decision was reached. A vector index of documents is enough when the need is "find similar text." Fine-tuning is the wrong default when the facts change.

## Sources

Do not refetch these to answer a pattern question.

- Google Cloud Architecture Center, "Choose a design pattern for your agentic AI system", reviewed 2026-05-28. https://docs.cloud.google.com/wiki/choose-design-pattern-agentic-ai-system
- Microsoft Azure Architecture Center, "AI Agent Orchestration Patterns". https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns
- Neo4j, "What is agentic AI architecture?", 2026-03-24. https://neo4j.com/blog/agentic-ai/agentic-architecture/
- Anthropic, "Building Effective AI Agents: Architecture Patterns and Implementation Frameworks" (PDF). https://resources.anthropic.com/hubfs/Building%20Effective%20AI%20Agents-%20Architecture%20Patterns%20and%20Implementation%20Frameworks.pdf
- Anthropic, "Building agents with Skills", 2026-01-22. https://claude.com/blog/building-agents-with-skills-equipping-agents-for-specialized-work
- Gulli, *Building AI Agents: From Design Patterns to Production* (Google Doc). Companion repo: https://github.com/agulli/atlas-agents. Distilled 2026-11-02. https://docs.google.com/document/d/1keM4ZbbfVmdsq3EAkbAliIegOpnnuBf-_KpD4oDOF0o

Business goals stay in the goal file the user passes to `architect-options`. They are not part of this library.
