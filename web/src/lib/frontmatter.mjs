/**
 * Enough YAML for a skill or agent frontmatter block. Nested maps are ignored.
 * @param {string} text
 * @returns {{ data: Record<string, string>, body: string }}
 */
export function splitFrontmatter(text) {
  const src = String(text).replace(/^\uFEFF/, "");
  const match = src.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n)*/);
  if (!match) return { data: {}, body: src };
  return { data: parseSimpleYaml(match[1]), body: src.slice(match[0].length) };
}

/**
 * @param {string} block
 * @returns {Record<string, string>}
 */
function parseSimpleYaml(block) {
  /** @type {Record<string, string>} */
  const data = {};
  const lines = block.split(/\r?\n/);
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    const field = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (!field) {
      index += 1;
      continue;
    }
    const key = field[1];
    const raw = field[2];
    if (raw === ">-" || raw === ">" || raw === "|" || raw === "|-") {
      /** @type {string[]} */
      const folded = [];
      index += 1;
      while (index < lines.length && /^( {2,}|\t)/.test(lines[index])) {
        folded.push(lines[index].trim());
        index += 1;
      }
      data[key] = raw.startsWith("|") ? folded.join("\n") : folded.join(" ").replace(/\s+/g, " ").trim();
      continue;
    }
    data[key] = raw.replace(/^["']|["']$/g, "").trim();
    index += 1;
  }
  return data;
}
