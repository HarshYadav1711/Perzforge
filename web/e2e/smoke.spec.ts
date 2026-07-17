import { test, expect } from "@playwright/test";

const email = process.env.E2E_EMAIL;
const password = process.env.E2E_PASSWORD;
const configured = Boolean(process.env.PLAYWRIGHT_BASE_URL && email && password);

test.describe("MVP smoke", () => {
  test.skip(!configured, "Set PLAYWRIGHT_BASE_URL, E2E_EMAIL, E2E_PASSWORD to run");

  test("login → submit job → see it on the list", async ({ page }) => {
    const jobName = `e2e-${Date.now()}`;

    await page.goto("/login");
    await page.getByTestId("login-email").fill(email!);
    await page.getByTestId("login-password").fill(password!);
    await page.getByTestId("login-submit").click();

    await expect(page).toHaveURL(/\/jobs/, { timeout: 15000 });

    await page.goto("/jobs/new");
    await page.getByTestId("job-name").fill(jobName);
    await page.getByTestId("job-submit").click();

    await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]+/, { timeout: 15000 });

    await page.goto("/jobs");
    await expect(page.getByTestId(`job-row-${jobName}`)).toBeVisible({ timeout: 15000 });
  });
});
