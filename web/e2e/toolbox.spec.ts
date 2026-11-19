import { readFileSync } from "node:fs";
import { test } from "@playwright/test";
import { cvFixture, jdFixture } from "./home";
import { assertPdf, Toolbox } from "./studio";

const experienceNote = "I used Helm at Brightfield to package two internal services";

test("tailor a pasted job to an uploaded CV and download the PDFs", async ({ page }) => {
  const job = readFileSync(jdFixture, "utf8");
  const toolbox = new Toolbox(page);

  await toolbox.open();
  await toolbox.chooseTailor();
  await toolbox.provideCv(cvFixture);
  await toolbox.pasteJob(job);
  await toolbox.startTailoring();
  await toolbox.finishUntilPdf(experienceNote);

  assertPdf(await toolbox.currentPdf());
  for (const layout of ["Classic", "Sidebar", "Modern"]) {
    assertPdf(await toolbox.layoutPdf(layout));
  }
});

test.fixme("polish a CV into downloadable PDFs", async () => {
  // Same PDF check, started from Polish a CV, once that path is in this suite.
});
