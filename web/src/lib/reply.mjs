/**
 * A recruiter email drawn only from a match report. Gaps are left out.
 * @param {string} report
 * @returns {{ markdown: string, role: string, attach: string }}
 */
export function draftReply(report) {
  const heading = (report.match(/^#\s+(.+)$/m) || [])[1] || "";
  const roleMatch = heading.match(/^Match report:\s*(.+?)\s+at\s+/i);
  const role = (roleMatch ? roleMatch[1] : heading.replace(/^Match report:\s*/i, "")).trim() || "the role";
  const attachLine = (report.match(/^-\s+Final PDF:\s*(\S+)/m) || [])[1] || "";
  const attach = attachLine.split("/").pop() || "cv.pdf";
  const name = firstName(attach);
  const strong = strongRequirements(section(report, "Coverage")).slice(0, 3);
  const claims = confirmedClaims(section(report, "Confirmed facts used")).slice(0, 4);
  const fit = [];
  if (strong.length > 0) fit.push(`The CV covers ${joinList(strong)}.`);
  if (claims.length > 0) fit.push(`Confirmed experience I can speak to: ${joinList(claims)}.`);
  if (fit.length === 0) fit.push("I have attached my CV for this role.");
  const lines = [
    "channel: email",
    "to:",
    `attach: ${attach}`,
    "",
    `Subject: ${role} — CV attached`,
    "",
    "Hi,",
    "",
    `I am writing about the ${role} role.`,
    "",
    ...fit,
    "",
    "I have attached my CV. Happy to talk.",
    "",
    name ? `Thanks,\n${name}` : "Thanks,",
    "",
  ];
  return { markdown: lines.join("\n"), role, attach };
}

/**
 * @param {string} filename
 */
function firstName(filename) {
  const token = filename.replace(/\.pdf$/i, "").split("-")[0];
  if (!token || token.length < 2 || /^cv$/i.test(token)) return "";
  return token;
}

/**
 * @param {string} report
 * @param {string} title
 */
function section(report, title) {
  const marker = `## ${title}`;
  const start = report.indexOf(marker);
  if (start < 0) return "";
  const rest = report.slice(start + marker.length);
  const next = rest.search(/\n## /);
  return next < 0 ? rest : rest.slice(0, next);
}

/**
 * @param {string} body
 * @returns {string[]}
 */
function strongRequirements(body) {
  /** @type {string[]} */
  const found = [];
  for (const row of tableRows(body)) {
    const strength = row[3] || "";
    const inPdf = row[5] || "";
    if (!strength.startsWith("strong") || !inPdf.startsWith("yes")) continue;
    const text = (row[0] || "").replace(/^req-\d+\s+/, "").trim();
    if (text) found.push(text);
  }
  return found;
}

/**
 * @param {string} body
 * @returns {string[]}
 */
function confirmedClaims(body) {
  /** @type {string[]} */
  const found = [];
  for (const row of tableRows(body)) {
    const claim = (row[1] || "").trim();
    if (claim && claim !== "Claim") found.push(claim);
  }
  return found;
}

/**
 * @param {string} body
 * @returns {string[][]}
 */
function tableRows(body) {
  /** @type {string[][]} */
  const rows = [];
  for (const line of body.split("\n")) {
    if (!line.startsWith("|") || /^\|\s*-+/.test(line)) continue;
    const cells = line.split("|").slice(1, -1).map((cell) => cell.trim());
    if (cells.length > 0 && cells[0] !== "Requirement" && cells[0] !== "ID") rows.push(cells);
  }
  return rows;
}

/**
 * @param {string[]} items
 */
function joinList(items) {
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}
