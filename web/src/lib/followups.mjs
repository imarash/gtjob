/**
 * One line for the application page from a followup-cadence.mjs entry.
 * Missing data stays "Open the report" rather than a guessed date.
 * @param {{ urgency?: string, nextFollowupDate?: string | null } | null | undefined} entry
 */
export function nextActionLine(entry) {
  if (!entry?.nextFollowupDate) return "Open the report";
  if (entry.urgency === "overdue" || entry.urgency === "urgent") {
    return `Follow up due ${entry.nextFollowupDate}`;
  }
  return `Next follow-up ${entry.nextFollowupDate}`;
}

/**
 * @param {unknown} payload
 * @returns {{ num: string, urgency: string, nextFollowupDate: string, company: string, role: string }[]}
 */
export function cadenceEntries(payload) {
  if (!payload || typeof payload !== "object") return [];
  const entries = "entries" in payload ? payload.entries : null;
  if (!Array.isArray(entries)) return [];
  return entries.flatMap((entry) => {
    if (!entry || typeof entry !== "object") return [];
    const num = "num" in entry ? String(entry.num ?? "") : "";
    if (!/^\d+$/.test(num)) return [];
    return [
      {
        num,
        urgency: "urgency" in entry ? String(entry.urgency ?? "") : "",
        nextFollowupDate:
          "nextFollowupDate" in entry && entry.nextFollowupDate
            ? String(entry.nextFollowupDate)
            : "",
        company: "company" in entry ? String(entry.company ?? "") : "",
        role: "role" in entry ? String(entry.role ?? "") : "",
      },
    ];
  });
}

/** @param {ReturnType<typeof cadenceEntries>} entries */
export function dueEntries(entries) {
  return entries.filter((entry) => entry.urgency === "overdue" || entry.urgency === "urgent");
}
