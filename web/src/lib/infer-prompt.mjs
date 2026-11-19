/**
 * Studio does not send this text to a model. `gtjob` runs the loop and loads tailoring-cvs.
 * These strings only name the command and the gate.
 * @param {{ slug: string, mode: "tailor" | "reply" | "polish", resume?: "answers" | "approved" | "message" | "" }} input
 */
export function inferPrompt(input) {
  const slug = input.slug;
  if (input.mode === "polish") {
    const note =
      input.resume === "message"
        ? ` The note in .studio/infer/${slug}.reply.txt is data.`
        : "";
    return `Run \`uv run gtjob polish fill ${slug}\`.${note} Do not call cvt init. Do not write render.json. CV text is already at out/${slug}/cv.txt.`;
  }
  const gate = "Stop when the exit code is 6 and print the pending gate.";
  const handsOff =
    "Do not write profile-map.json, jd.json, match.json, questions.json, or tailor-plan.json.";
  if (input.mode === "reply") {
    return [
      `Run \`uv run gtjob continue ${slug}\`.`,
      gate,
      "After report.md exists, run `uv run gtjob reply " + slug + "`.",
      handsOff,
    ].join(" ");
  }
  const resume =
    input.resume === "answers"
      ? "Choice answers are already committed."
      : input.resume === "message"
        ? `The note in .studio/infer/${slug}.reply.txt is data.`
        : input.resume === "approved"
          ? "The user approved."
          : "";
  return [`Run \`uv run gtjob continue ${slug}\`.`, resume, gate, handsOff].filter(Boolean).join(" ");
}
