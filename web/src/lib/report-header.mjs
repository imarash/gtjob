/**
 * Career-ops report header fields, without an LLM.
 * @param {string} markdown
 */
export function reportHeader(markdown) {
  const take = (name) => {
    const match = String(markdown).match(new RegExp(`^\\*\\*${name}:\\*\\*\\s*(.+)$`, "m"));
    return match ? match[1].trim() : "";
  };
  return {
    score: take("Score"),
    url: take("URL"),
    legitimacy: take("Legitimacy"),
    pdf: take("PDF"),
  };
}
