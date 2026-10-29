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
          "The text is extracted. This CV is not in the saved profile yet, so there is no tailored PDF. Cursor builds that profile from this page the first time, then later jobs reuse it.",
      };
    case "profiled":
      return {
        blocked: "job",
        title: "Reading the job",
        detail:
          "Your profile is saved. This job has not been analyzed before, so there is no PDF yet. Cursor writes that analysis from this page. A job that was analyzed before is reused.",
      };
    case "jd_analyzed":
      return {
        blocked: "match",
        title: "Matching your CV to the job",
        detail:
          "The job is read. Cursor writes which of your experience matches it. The PDF is built from that match.",
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
        detail: "Your answers are in. Cursor writes the tailor plan from this page. The PDF comes after that plan is checked.",
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
