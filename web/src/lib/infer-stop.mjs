/**
 * A fresh run stops at the first checkpoint so the person can answer.
 * A resumed run starts already at that checkpoint and has to be allowed to work through it.
 * @param {string} stage
 * @param {string} startStage
 * @param {string} resume
 * @param {boolean} seenOtherStage
 * @returns {{ stop: boolean, seenOtherStage: boolean }}
 */
export function stopAtCheckpoint(stage, startStage, resume, seenOtherStage) {
  const checkpoint = stage === "awaiting_answers" || stage === "awaiting_approval";
  const moved = seenOtherStage || Boolean(startStage && stage && stage !== startStage && !checkpoint);
  if (!checkpoint) return { stop: false, seenOtherStage: moved };
  if (!resume) return { stop: true, seenOtherStage: moved };
  if (stage === startStage && !seenOtherStage) return { stop: false, seenOtherStage: false };
  if (resume === "approved" && stage === "awaiting_approval") return { stop: false, seenOtherStage: true };
  return { stop: true, seenOtherStage: true };
}
