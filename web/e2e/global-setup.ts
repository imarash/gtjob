import { mkdir, rm } from "node:fs/promises";
import path from "node:path";
import { e2eHome } from "./home";

export default async function globalSetup() {
  await rm(e2eHome, { recursive: true, force: true });
  await mkdir(path.join(e2eHome, "CVs"), { recursive: true });
  await mkdir(path.join(e2eHome, "JDs"), { recursive: true });
  await mkdir(path.join(e2eHome, "out"), { recursive: true });
}
