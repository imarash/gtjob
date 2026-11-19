function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inline(escaped) {
  let text = escaped;
  text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(
    /\[([^\]]+)\]\(([^)\s]+)\)/g,
    (_match, label, href) => {
      if (!/^https?:\/\//i.test(href) && !/^[^:\s]+$/.test(href)) return label;
      if (/^\s*javascript:/i.test(href)) return label;
      return `<a href="${href}">${label}</a>`;
    },
  );
  return text;
}

/**
 * Render a report to HTML. The source is escaped before any tag is added,
 * so a raw HTML block in the file cannot become a tag.
 * @param {string} markdown
 */
export function renderMarkdown(markdown) {
  const lines = String(markdown).replace(/\r\n/g, "\n").split("\n");
  /** @type {string[]} */
  const out = [];
  let index = 0;
  const flushParagraph = (buffer) => {
    if (buffer.length === 0) return;
    out.push(`<p>${inline(escapeHtml(buffer.join(" ")))}</p>`);
    buffer.length = 0;
  };
  /** @type {string[]} */
  const paragraph = [];
  while (index < lines.length) {
    const line = lines[index];
    if (line.startsWith("```")) {
      flushParagraph(paragraph);
      const body = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        body.push(escapeHtml(lines[index]));
        index += 1;
      }
      out.push(`<pre><code>${body.join("\n")}</code></pre>`);
      index += 1;
      continue;
    }
    if (/^\s*\|/.test(line) && index + 1 < lines.length && /^\s*\|?\s*-+/.test(lines[index + 1])) {
      flushParagraph(paragraph);
      const rows = [];
      while (index < lines.length && /^\s*\|/.test(lines[index])) {
        rows.push(lineCells(lines[index]));
        index += 1;
      }
      const [header, _divider, ...body] = rows;
      if (!header) continue;
      const head = header.map((cell) => `<th>${inline(escapeHtml(cell))}</th>`).join("");
      const bodyHtml = body
        .filter((row) => !row.every((cell) => /^:?-+:?$/.test(cell)))
        .map(
          (row) =>
            `<tr>${row.map((cell) => `<td>${inline(escapeHtml(cell))}</td>`).join("")}</tr>`,
        )
        .join("");
      out.push(`<table><thead><tr>${head}</tr></thead><tbody>${bodyHtml}</tbody></table>`);
      continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.*)$/);
    if (heading) {
      flushParagraph(paragraph);
      const level = heading[1].length;
      out.push(`<h${level}>${inline(escapeHtml(heading[2]))}</h${level}>`);
      index += 1;
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      flushParagraph(paragraph);
      const items = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(inline(escapeHtml(lines[index].replace(/^\s*[-*]\s+/, ""))));
        index += 1;
      }
      out.push(`<ul>${items.map((item) => `<li>${item}</li>`).join("")}</ul>`);
      continue;
    }
    if (line.trim() === "") {
      flushParagraph(paragraph);
      index += 1;
      continue;
    }
    paragraph.push(line.trim());
    index += 1;
  }
  flushParagraph(paragraph);
  return out.join("\n");
}

/** @param {string} line */
function lineCells(line) {
  const parts = line.split("|").map((cell) => cell.trim());
  return parts.slice(1, line.trimEnd().endsWith("|") ? -1 : undefined);
}
