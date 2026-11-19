import path from "node:path";

/** Isolated cvt workspace. Studio reads it when GTJOB_HOME is set. */
export const e2eHome = path.resolve(process.cwd(), ".e2e-home");

export const e2ePort = Number(process.env.GTJOB_E2E_PORT || 3857);

export const repoRoot = path.resolve(process.cwd(), "..");

export const fakeLlmDir = path.join(repoRoot, "tests", "e2e", "fake_llm");

export const cvFixture = path.join(repoRoot, "tests", "fixtures", "cv", "jamie-rivera-junior.txt");

export const jdFixture = path.join(repoRoot, "tests", "fixtures", "jds", "junior-devops-engineer.md");
