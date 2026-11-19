import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { resolvePaths } from "../src/lib/paths.mjs";

test("GTJOB_HOME moves runs and uploads off the repo", () => {
  const repo = "/tmp/gtjob-repo";
  const home = "/tmp/gtjob-home";
  const paths = resolvePaths(repo, { GTJOB_HOME: home });
  assert.equal(paths.gtjobRoot, path.resolve(repo));
  assert.equal(paths.workspaceRoot, path.resolve(home));
  assert.equal(paths.outDir, path.join(path.resolve(home), "out"));
  assert.equal(paths.inboxPath, path.join(path.resolve(home), ".studio", "inbox.json"));
});

test("without GTJOB_HOME the workspace is the repo", () => {
  const paths = resolvePaths("/tmp/gtjob-repo", {});
  assert.equal(paths.workspaceRoot, paths.gtjobRoot);
  assert.equal(paths.outDir, path.join(paths.gtjobRoot, "out"));
});
