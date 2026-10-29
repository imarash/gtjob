# Planning prompt: SaaS job-apply platform

> How to use: from the gtjob repo root, open a new Agent chat, attach this file (`@prompts/saas-job-apply-plan.md`), and say "execute this prompt".
>
> This session writes the plan. It does not implement the product, open a pull request, or create a new repository. A later chat builds from `plan/saas/STATUS.md`.

---

<role>
You are the product architect for a job-search product that will become a paid SaaS. You study three local checkouts, decide what each one is good for, and write an execution plan for one intuitive product. The first build is something one person can use on this machine. Accounts and payments come after that loop works. The customer never has to know the three repos exist.

You plan. You do not write product code, migrations, billing integrations, or marketing pages. Workers in a later session will not see this conversation, so every decision they need lives in the plan files you write.
</role>

<objective>
Produce a plan for one product a person can run before accounts and payments exist, and that later becomes the hosted SaaS in `<pricing>`.

The first hour of the product is a CV, then jobs, then a reply:

1. The person uploads a PDF CV. That file is the original, and it stays. They can polish it, with no job description, into a second base CV. Polish keeps every fact. Both bases remain available.
2. Jobs arrive from the journeys in `<journeys>`. Each job lands in one queue. The person picks the original or the polished CV as the source, then tailors a truthful CV for that job, or sends the polished one as-is when the job needs no rewrite.
3. The queue shows which jobs they saved, which they marked applied, and which a person or a company sent to them. Status is something they set. The product prepares the CV and a reply. They send it.
4. Pricing, samples, and the refund rule in `<pricing>` are part of the business plan. Signup, sessions, and card charging are specified and then scheduled after the loop works. This plan does not make them the first build.

The product should feel like one place: your CV, the jobs in front of you, the next reply. ApplyTrace (https://applytrace.com/) is the bar for calm tracking. jlog (https://jlog.ai/) is the closer 2026 workflow: capture a job, fill what is safe, track it, tailor from real lines, and leave submit to the person. Tsenta (YC S26, https://www.ycombinator.com/companies/tsenta) is the market pattern of match, rewrite, and apply-for-you. Study it. Do not copy the auto-apply.

Depth (fit, live posting, fact-checked CV) sits behind the calm. The three repos are the raw material. The customer never has to learn their names.
</objective>

<pricing>
Lock these numbers. The plan may explain a risk. It may not quietly replace them.

| Plan | Price | Allowance |
| --- | --- | --- |
| Sample | $0, no card | 3 job descriptions, once per account, for the life of the account |
| Monthly | $10 per month | 30 job descriptions per calendar month |
| Yearly | $72 per year | The same 30 job descriptions per calendar month, billed once a year |

- Uploading a CV and polishing it do not consume a job description. A polished CV is a second base document, not a job.
- A job description is consumed the first time the account tailors a CV for that job. Sending the original or the already-polished CV, opening the job again, changing its status, drafting a reply that attaches an existing PDF, and downloading the same PDF again consume nothing.
- Say which output the meter counts if v1 cannot tailor yet. The default is the tailored CV. Fit-only is a fallback you must justify with the cost math.
- Unused monthly allowance expires at the end of the calendar month. The yearly plan is a discount on the same monthly cap. It is not a pool of 360 job descriptions.
- 30-day money-back guarantee on the first charge only, monthly or yearly. The person gets the fee back if they ask within 30 days of that charge. Later renewals are not covered. Using some of the month's allowance does not cancel the guarantee.
- Cancel stops the next charge. Access continues until the period already paid for ends, except when the guarantee refunds the first charge, in which case paid access ends when the refund is issued.
- One paid tier in v1. Extra tiers, team seats, and overage packs are named only as later options, with no prices invented for them.

The plan states, in one short public-facing paragraph, what a visitor reads on the pricing page: 3 free samples, $10/month or $72/year for 30 jobs a month, 30-day money-back on the first payment. No other offer.
</pricing>

<repos>
Three checkouts sit next to each other. Verify each path before you rely on it. Read them. Do not edit them. Do not copy trees into the plan.

| Checkout | Path | What it already is |
| --- | --- | --- |
| gtjob | current working directory | Truthful CV tailoring. Python CLI, `cvt`, skills under `.claude/skills/`. Runs in `out/<slug>/`, confirmed facts in `profiles/`. Studio, the local Next.js app in `web/`, shows runs and, when `CAREER_OPS_ROOT` is set, the career-ops tracker. |
| career-ops | `../career-ops` | Local-first job-search agent. Markdown tracker, evaluation, portal scan, liveness, follow-ups, interview prep, assisted apply that never submits. MIT. |
| dossier | `../dossier` | Self-hosted Next.js and Postgres product: one profile, tailored resume and cover letter, kanban, find-jobs, optional Gmail and calendar, funnel dashboard. AGPL-3.0. |

Known starting points. Verify them, then extend the inventory with what you actually find. Miss nothing load-bearing, and do not treat this list as complete.

gtjob:

- `README.md`, `plan/v2/ARCHITECTURE.md`, `plan/v2/STATUS.md`, `web/README.md`
- Tailoring skill and `cvt`: fact gate, gap questions, approval, PDF, match report
- `cv-polish` and the tailoring skill's no-JD path: a generic polish that keeps every fact. Read `.claude/skills/cv-polish/SKILL.md` and the generic-CV reference the tailoring skill points at.
- Studio routes: Today, saved roles (`.studio/inbox.json`), Applications, Runs, Toolbox, Settings
- The gap already observed: **Add a role** stores text in the inbox and does not create an application. Applications appear only after a career-ops tracker file exists. `data/applications.md` and `data/pipeline.md` were absent in the career-ops checkout when that gap was last checked. Confirm the current files yourself.

career-ops:

- `AGENTS.md` sections Data Contract, Source-of-Truth Boundary, Ethical Use, Offer Verification, LinkedIn JD loading guard
- `data/pipeline.md` as the URL inbox, `data/applications.md` as the tracker, `set-status.mjs`, `templates/states.yml`
- Evaluation and legitimacy, `check-liveness.mjs`, portal scan, follow-up cadence
- `web/` as a local view over the same files. Study how it calls scripts. Leave that UI where it is.
- `docs/LINKEDIN_JOIN.md`: a connections export that answers "do I know someone here?" It does not import saved jobs.

dossier, read for interaction design only:

- `README.md` features and screen list
- The shape of an application (posting, match, documents, status history, next interview, notes) and the find-jobs, inbox, and dashboard screens
- Prisma and React source stay unread beyond what you need to name a capability. Do not paste schema or components into the plan.
</repos>

<license_boundary>
The product is a commercial hosted service. The plan chooses a license path and sticks to it.

- career-ops is MIT. gtjob's tailoring skill is MIT. MIT code may be called, ported, or run as a service inside the SaaS if copyright notices stay with the code. Say which of those three you mean for each module.
- dossier is AGPL-3.0. Use it as a read-only reference for screens and for the fields an application needs. New code is written fresh. Vendoring, linking, or translating dossier source into the SaaS is out of the plan. If a later decision wants dossier code, that decision has to say the service would offer corresponding source to every user, and it has to wait for an explicit yes. This plan does not assume that yes.
- Record the license of every new dependency you propose to ship, including UI kits, job-data APIs, model providers, and billing.
- Personal trees stay out of the plan and out of any example: `CVs/`, `JDs/`, `out/`, `profiles/`, `.studio/`, career-ops `data/`, dossier database contents. Use synthetic examples.
</license_boundary>

<product_rules>
These hold for every screen and every later build slice.

1. **Facts.** A CV bullet, skill, date, or metric comes from the person's profile, their CV, or a confirmation they recorded. Gaps stay gaps.
2. **One queue.** The customer sees one list of jobs. Internal words such as inbox.json, pipeline.md, career-ops, cvt, and dossier never appear in the product UI.
3. **The person sends.** The product may draft, tailor, and open a PDF. No version in this plan clicks Submit, Send, or Apply on an employer form.
4. **Postings are data.** Text fetched from a URL or pasted into a form cannot change instructions, write outside the job it belongs to, or reveal secrets.
5. **Live or unknown.** The product tells the person a job is open or closed only from a real check it can name. Otherwise it says the posting has not been checked.
6. **Quality over volume.** A weak fit is labeled as a weak fit. The product does not push the person to apply anyway.
7. **Two bases, many jobs.** The original PDF and the polished CV both survive. A tailored CV for a job is a third file, tied to that job, and it records which base it came from. Later tailors can start from either base.
8. **LinkedIn and other boards.** The permitted ways in are the ones in `<journeys>`: clip the posting the person is looking at, paste a URL or text, or import a file LinkedIn's own "Download your data" screen currently offers. A login scraper, a stored LinkedIn password, or a session cookie is out of the plan. Verify the archive categories against LinkedIn's current help page before naming a file the product accepts. As of the research behind this prompt, "Job Applications" is a documented category (date, company, title, LinkedIn URL). "Saved Jobs" was not confirmed on that table; treat it as present only if the page you open lists it.
9. **Privacy.** A CV is the customer's data. The plan says how a person exports and deletes everything, and what a model provider receives when a CV is polished or a job is tailored. Account isolation is part of the later auth slice. Until that slice, the plan describes a single-user local build.
</product_rules>

<journeys>
Design these as stories in `PLAN.md`, each with the screen, the primary action, and whether it is in the first build or later. Use a synthetic candidate and a synthetic job. The first three are the product. The rest are the 2026 intake patterns worth planning now so the queue does not grow a second list later.

**First session.** Upload a PDF CV. See it as the original. Run polish. Keep both. The empty jobs list invites the next action: add a job. Samples and prices can be visible as copy. Nothing in this session requires an account or a card.

**Use either CV on a job.** The person adds a job description. They choose Original or Polished. Tailor produces a CV for that job only. The job remembers which file they would send.

**Reply.** A job can be one they found, or one that found them (a recruiter email, a referral, an inbound message). From the job they draft a short reply and attach either the polished CV or the tailored one. The draft is copied or opened in their mail app. The product does not send it. Marking the job Applied, Replied, or Interview stays a click they make.

**Add by hand.** Paste the description, or paste a URL. When the URL can be read safely, fetch the description and show it. When it cannot, ask them to paste the text. This is the first way jobs enter.

**Clip while browsing.** Huntr, Teal, Simplify, Careerflow, Jobotrak, jlog, and Tsenta all use a browser extension because LinkedIn and the other boards do not hand a third party the saved-jobs list. The plan designs a later clipper: the person is on a posting, one click saves company, title, URL, and description into the same queue, and says so if that posting is already there. v1 can ship without the extension. The queue's data shape has to accept a clipped job without a migration.

**LinkedIn archive.** The person downloads their data from LinkedIn Settings and drops the file in. Import "Job Applications" as jobs already marked applied, when that category is still what LinkedIn documents. Import "Saved Jobs" only when the current help page lists that category; otherwise say the clipper and paste are the way to bring saved jobs across. The Member Data Portability API is a later option for members in the EU, EEA, and Switzerland only, per LinkedIn's own help. Connections export stays the career-ops "do I know someone here?" idea, and it is later.

**Find.** A search over boards the person chose, saved into the same queue, dismissed jobs staying dismissed. career-ops portal scan is the MIT source to study. A third-party job API is a cost line in the unit economics, not a default dependency. Finding jobs is later than paste and tailor.

**Inbound mail.** Pasting a recruiter email is in the first build, beside paste-a-JD. A personal forward-to address, and a Gmail connection that files employer replies on the job, are later. Dossier's inbox is the interaction reference. The code is written fresh. The reply draft can attach the polished CV or a tailored one.

**One card for one job.** The same role saved from LinkedIn and from the employer's board becomes one card. The plan says how identity is judged (employer URL, then company plus title, with a req id when both sides have one).

**After they send.** The job stores which PDF went out. A follow-up is due when a replied or applied job goes quiet. An interview date sits on the card. A home list is "needs you": replies to finish, follow-ups due, jobs saved and not yet decided. Interview prep from the same facts is later.

For each later journey, name the 2026 product that does it well and the part this product refuses. Auto-apply, mass submit, and invented CV lines are the refusals, even when a YC company ships them.
</journeys>

<kpis>
The plan includes a KPI section a founder can run the company on. Define each metric in one sentence, name the source (product event, billing, support), and name the first target as a hypothesis, marked as a hypothesis.

Cover at least:

- **North star.** A person completing a truthful tailored CV for a real job they then mark as applied or replied. Count people who do that in a month, not jobs submitted by a bot.
- **Activation.** People who upload a CV. Of those, who finish a polish. Of those, who tailor sample 1. Of those, who finish all 3 samples. Until accounts exist, "people" means completed local sessions you can count without a login.
- **Conversion.** Sample accounts who pay within 14 days.
- **Revenue.** MRR, ARR, share of accounts on yearly, ARPU, net revenue after refunds.
- **Retention.** Logo churn and revenue churn per month. Share of paid accounts still paid in month 2.
- **Guarantee.** Refunds divided by first charges, monthly and yearly shown apart.
- **Usage.** Job descriptions used divided by job descriptions entitled, for paid accounts.
- **Unit economics.** Model and job-data cost per consumed job description. Gross margin on a $10 account that uses all 30, and on a $72 account that uses 30 every month for a year. The break-even cost per job description. If today's tailoring path costs more than the price can bear, say so and name the cheapest v1 output that still keeps the promise, or the cap that keeps a stated margin. Show the arithmetic.
- **Product quality.** Time from "add a job" to a downloadable PDF. Share of jobs that reach a PDF. Share of tailored jobs the person marks applied within 14 days.
- **Trust.** Support contacts per 100 accounts. Jobs where the person corrects or rejects a fabricated-feeling claim.

Guardrail: no KPI that rewards automatic applications, keyword stuffing, or invented experience. A score below the bar the current product already uses (under 4.0/5 where that scale remains) stays a "think twice" signal, not a growth tactic.
</kpis>

<decisions>
For every capability below, write one row after you have read the code that implements it today. Columns: capability, best source today, license, SaaS choice, why, v1 or later.

SaaS choice is one of: **call** (run the existing MIT tool as a worker), **port** (rewrite the behavior in the SaaS codebase, MIT only), **reimplement** (new code, required for anything learned from dossier), **drop**.

Cover at least: PDF CV upload, original kept, polish with no job description, choose original or polished as the tailor source, add a job by paste, fetch a job description from a URL, live-posting check, fit and legitimacy, one queue with saved versus applied versus inbound, reply draft with a chosen PDF, tailored CV and fact check, match report, which PDF was sent, browser clipper, LinkedIn data-download import, portal discovery, forwarded recruiter mail, Gmail replies, calendar, follow-up reminder, cover letter, accounts, billing, export and delete.

Accounts and billing get rows. Their SaaS choice is **reimplement**, and the phase is **later**, after the CV and queue loop. The plan still specifies them. The first build does not include them.

Add rows for strong modules you find that this list missed. A module you drop still gets a row and a reason.
</decisions>

<architecture>
Recommend where the SaaS code lives (this repo, or a new repo later) and stop there. Do not create the repo.

The local apps are single-user and file-based. Hosted multi-tenant service is a different shape. Describe both, and build the first slices on the local shape.

- Documents: original PDF, polished CV, and per-job tailored CVs, each pointing at the base it came from. Jobs: source (pasted, URL, clip, archive import, search, inbound), status, the PDF chosen to send, and a reply draft. Status history and a usage ledger. Enough fields for the first loop and for accounts later. No copied Prisma file.
- How a consumed job description is counted, idempotently, including retries. Polish and replies that attach an existing PDF stay off that counter.
- What stays on the customer's machine versus what a model sees during polish and during tailor.
- The first-loop screens, in the customer's words: CV, Jobs, Job, Reply. Home is the "needs you" list once more than one job exists. Pricing and Account are specified screens for the later slices. For each screen, the one primary action and the empty state.
- Auth and payment, written so a later session can build them, and ordered after the loop: magic link or passkey through a hosted auth provider, not a hand-rolled password system. Stripe Checkout and the Customer Portal, not a custom card form. Map the sample allowance, the $10 monthly price, the $72 yearly price, and the 30-day first-charge refund. Name the webhook events that change entitlement. This session does not implement them, and the first build slices do not either.
- Ordered slices. The first slice is one person on the local app, with no signup and no payment: upload a PDF, polish it, keep both, paste one job description, tailor from the chosen base, see that job on the queue, draft a reply that attaches a CV. URL fetch, queue statuses, the clipper, the LinkedIn archive import, find-jobs, inbound mail connection, accounts, and billing follow in the order you justify. Public launch is the slice that turns on auth and the prices together.
</architecture>

<this_session>
Write only these files:

1. `plan/saas/PLAN.md` — the product, the loop, the screens, the architecture, the phased slices, the risks, and the open questions. A founder and an engineer can both read it. About 8–15 pages of substance, not a tour of the three repos.
2. `plan/saas/DECISIONS.md` — the capability table from `<decisions>`, plus the license path in a short preamble.
3. `plan/saas/KPIS.md` — definitions, hypotheses, the pricing paragraph, and the unit-economics arithmetic. State the inputs you measured or estimated, and mark estimates.
4. `plan/saas/STATUS.md` — this session marked done, the first build slice named, and a one-line resume point for the next chat.

Do not edit `plan/v2/`, `plan/PLAN.md`, product code, `../career-ops`, or `../dossier`. Do not commit unless the user asks in that later chat. This prompt does not ask you to commit.

If a checkout is missing or a license is different from what this prompt says, record the fact and plan against what you found. Do not invent a module to fill the gap.
</this_session>

<quality_bar>
- Every "we will reuse X" points at a file you opened.
- Every cost figure shows its formula.
- The customer's first session is a story of a few minutes: upload a synthetic CV, polish it, paste one synthetic job, choose which base to tailor from, draft a reply, and see the job once in the queue. The three-sample count is specified for the billing slice. It is not a gate on that first story.
- The plan says how the current Studio confusion ends: one queue, one status, one next action. A saved role, a found role, an inbound message, and an applied job are states of that queue, not separate products. Original, polished, and tailored are documents on the person or on the job, not separate apps.
- Open questions are few, each with a default the next session may follow if nobody answers.
</quality_bar>
