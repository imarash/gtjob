/** Display columns. The stored status stays the career-ops token. */

export const BOARD_COLUMNS = [
  { id: "review", label: "Review", states: ["Evaluated"] },
  { id: "progress", label: "In progress", states: ["Applied", "Responded", "Assessment"] },
  { id: "interview", label: "Interview", states: ["Interview"] },
  { id: "offer", label: "Offer", states: ["Offer", "Hired"] },
  { id: "closed", label: "Closed", states: ["Rejected", "Discarded", "SKIP"] },
];

export function columnForStatus(status) {
  return (
    BOARD_COLUMNS.find((column) => column.states.includes(status)) ?? {
      id: "other",
      label: "Other",
      states: [],
    }
  );
}

/** @param {string} score */
export function scoreNumber(score) {
  const text = String(score ?? "").trim();
  const fraction = text.match(/^(\d+(?:\.\d+)?)\s*\/\s*5$/);
  if (fraction) return Number(fraction[1]);
  return null;
}

/** Scores below 4.0/5 stay visibly "do not apply". Sentinels are not scores. */
export function belowApplyBar(score) {
  const value = scoreNumber(score);
  return value != null && value < 4;
}
