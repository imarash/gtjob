/**
 * What to tell a person about a run stage. Never a shell command.
 * @param {string} stage
 * @returns {{ blocked: string, title: string, detail: string }}
 */
export function describeStage(stage) {
  switch (stage) {
    case "initialized":
    case "ingested":
      return {
        blocked: "profile",
        title: "Reading your CV",
        detail:
          "The text is extracted. This CV is not in the saved profile yet, so there is no tailored PDF. The profile is built from this page the first time, then later jobs reuse it.",
      };
    case "profiled":
      return {
        blocked: "job",
        title: "Reading the job",
        detail:
          "Your profile is saved. This job has not been analyzed before, so there is no PDF yet. The job analysis is written from this page. A job that was analyzed before is reused.",
      };
    case "jd_analyzed":
      return {
        blocked: "match",
        title: "Matching your CV to the job",
        detail:
          "The job is read. The next step writes which of your experience matches it. The PDF is built from that match.",
      };
    case "matched":
    case "awaiting_answers":
      return {
        blocked: "questions",
        title: "A few questions",
        detail: "A few questions are waiting before the PDF can be built.",
      };
    case "answers_applied":
      return {
        blocked: "tailor",
        title: "Writing the CV",
        detail: "Your answers are in. The tailor plan is written from this page. The PDF comes after that plan is checked.",
      };
    case "tailored":
    case "awaiting_approval":
      return {
        blocked: "approve",
        title: "Ready for your approval",
        detail: "Review the changes on the run and approve them. Studio can render the PDF after that.",
      };
    case "approved":
    case "rendered":
      return {
        blocked: "render",
        title: "Rendering",
        detail: "The CV is approved. Render it from the run page if the preview is not here yet.",
      };
    case "validated":
    case "reported":
      return {
        blocked: "ready",
        title: "Ready",
        detail: "Preview the PDF, download it, and use the reply beside it. Nothing is sent.",
      };
    default:
      return {
        blocked: "wait",
        title: "Not ready",
        detail: "This run does not have a tailored PDF yet.",
      };
  }
}

/**
 * @param {string} stage
 */
export function stepIndex(stage) {
  if (stage === "initialized" || stage === "ingested") return 0;
  if (stage === "profiled") return 1;
  if (stage === "jd_analyzed") return 2;
  if (
    stage === "matched" ||
    stage === "awaiting_answers" ||
    stage === "answers_applied" ||
    stage === "tailored" ||
    stage === "awaiting_approval"
  ) {
    return 3;
  }
  if (stage === "approved" || stage === "rendered" || stage === "validated" || stage === "reported") return 4;
  return 0;
}

export const STEP_LABELS = ["Extract", "Profile", "Job", "Match", "PDF"];

/**
 * The step being worked on. The saved stage is the last finished one, so a run
 * at `profiled` is already reading the job.
 * @param {string} stage
 */
export function activeStep(stage) {
  if (stage === "profiled") return 2;
  if (stage === "jd_analyzed") return 3;
  return stepIndex(stage);
}

/**
 * One sentence for the long wait on a step. Never a shell command.
 * @param {string} stage
 */
export function waitDetail(stage) {
  if (stage === "initialized" || stage === "ingested" || stage === "") {
    return "Reading the CV. This step often takes a few minutes.";
  }
  if (stage === "profiled") return "Reading the job. This step often takes a few minutes.";
  if (stage === "jd_analyzed") return "Matching your experience to the posting.";
  if (stage === "matched" || stage === "awaiting_answers") {
    return "Preparing the questions.";
  }
  if (stage === "answers_applied" || stage === "tailored" || stage === "awaiting_approval") {
    return "Writing the draft from the match.";
  }
  if (stage === "approved" || stage === "rendered" || stage === "validated" || stage === "reported") {
    return "Rendering the PDF.";
  }
  return "Working through this CV. This usually takes a few minutes.";
}
