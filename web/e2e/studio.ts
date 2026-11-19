import { expect, type Locator, type Page } from "@playwright/test";

/**
 * Toolbox outcomes. Locators use roles and names, so a later visual pass
 * (a Gamma-style CV, a new chrome) changes this file and not the scenario.
 */
export class Toolbox {
  constructor(private readonly page: Page) {}

  async open() {
    await this.page.goto("/toolbox");
    await expect(this.page.getByRole("heading", { name: "Toolbox" })).toBeVisible();
  }

  async chooseTailor() {
    await this.page.getByRole("button", { name: "Tailor to a job" }).click();
  }

  async provideCv(file: string) {
    const uploaded = this.page.waitForResponse(
      (response) => response.url().includes("/api/uploads") && response.request().method() === "POST",
    );
    await this.page.getByLabel("Upload a CV").setInputFiles(file);
    const response = await uploaded;
    expect(response.ok()).toBeTruthy();
  }

  async pasteJob(text: string) {
    const box = this.page.getByRole("textbox", { name: /job text|paste the job/i });
    await box.evaluate((element, value) => {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
      setter?.call(element, value);
      element.dispatchEvent(new Event("input", { bubbles: true }));
    }, text);
    await expect(box).toHaveValue(text);
  }

  async startTailoring() {
    const reply = this.page.getByRole("checkbox", { name: "Write a reply" });
    if (await reply.isChecked()) await reply.uncheck();
    const start = this.page.getByRole("button", { name: "Start tailoring" });
    await expect(start).toBeEnabled();
    await start.click();
  }

  /**
   * Walk whatever gate is on screen until a PDF can be downloaded.
   * A written note is one gate. Approving the draft is the other.
   */
  async finishUntilPdf(reply: string) {
    const approve = this.page.getByRole("button", { name: /approve and render/i });
    const apply = this.page.getByRole("button", { name: /apply answers/i });
    const download = this.downloadLink();
    const message = this.page.getByRole("textbox", { name: "Message" });
    const failure = this.page.getByRole("log", { name: "Conversation" }).getByText(/error\[/);
    let noted = false;

    const ready = async () => {
      if (await failure.isVisible()) return "failure";
      if (await download.isVisible()) return "download";
      if ((await approve.isVisible()) && (await approve.isEnabled())) return "approve";
      if (!noted && (await message.isVisible()) && (await message.isEnabled()) && (await apply.isVisible())) return "note";
      if ((await apply.isVisible()) && (await apply.isEnabled())) return "apply";
      return "";
    };

    for (let step = 0; step < 6; step += 1) {
      let kind = "";
      await expect
        .poll(async () => {
          kind = await ready();
          return kind;
        })
        .not.toBe("");
      if (kind === "failure") throw new Error(await failure.innerText());
      if (kind === "download") return;
      if (kind === "approve") {
        await approve.click();
        await expect(download).toBeVisible();
        return;
      }
      if (kind === "note") {
        noted = true;
        await message.fill(reply);
        await this.page.getByRole("button", { name: "Send" }).click();
        await expect(message).toBeDisabled();
        continue;
      }
      await apply.click();
      await expect(apply).toBeDisabled({ timeout: 15_000 }).catch(() => undefined);
    }
    const visible = await this.page.locator("main").innerText();
    throw new Error(`Tailoring did not reach a PDF.\n${visible.slice(0, 2000)}`);
  }

  /** The PDF offered before a layout is chosen. */
  async currentPdf(): Promise<Buffer> {
    return this.readDownload();
  }

  /** Choose a named layout and read the PDF that download points at. */
  async layoutPdf(name: string): Promise<Buffer> {
    const href = this.downloadLink();
    const pattern = new RegExp(`${name}\\.pdf`, "i");
    const layouts = this.page.locator("section").filter({ hasText: "Choose a layout" });
    await layouts.getByRole("button", { name: new RegExp(`^${name}\\b`, "i") }).click();
    await expect(href).toHaveAttribute("href", pattern);
    return this.readDownload();
  }

  private async readDownload(): Promise<Buffer> {
    const href = await this.downloadLink().getAttribute("href");
    if (!href) throw new Error("No PDF download is on the page.");
    const response = await this.page.request.get(href);
    expect(response.ok()).toBeTruthy();
    expect(response.headers()["content-type"] ?? "").toContain("pdf");
    return response.body();
  }

  private downloadLink(): Locator {
    return this.page.getByRole("link", { name: /download pdf/i });
  }
}

export function assertPdf(bytes: Buffer) {
  expect(bytes.subarray(0, 5).toString("utf8")).toBe("%PDF-");
  expect(bytes.length).toBeGreaterThan(1000);
}
