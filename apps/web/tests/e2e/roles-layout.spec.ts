import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { apiToken, login, noHorizontalOverflow } from "./helpers";

const ROLES = ["superadmin", "gp.vanapuram", "collector1", "driver.vanapuram", "mrf.operator", "processor", "household", "evaluator"];

test("every demo role can sign in and lands on a working page", async ({ page }) => {
  for (const who of ROLES) {
    await login(page, who);
    await expect(page.locator("main h1").first()).toBeVisible();
    await expect(page.getByText("Something went wrong")).toHaveCount(0);
    await page.context().clearCookies();
    await page.evaluate(() => localStorage.clear());
  }
});

test("roles are enforced by the API, not just hidden in the UI", async ({ request }) => {
  const headers = { Authorization: `Bearer ${await apiToken(request, "collector1")}` };
  expect((await request.get("/api/v1/users", { headers })).status()).toBe(403);
  expect((await request.get("/api/v1/finance/summary", { headers })).status()).toBe(403);
  const evaluator = { Authorization: `Bearer ${await apiToken(request, "evaluator")}` };
  expect((await request.get("/api/v1/analytics/overview", { headers: evaluator })).ok()).toBeTruthy();
  expect((await request.post("/api/v1/vehicles", { headers: evaluator, data: {} })).status()).toBe(403);
});

for (const width of [360, 768, 1440]) {
  test(`no horizontal overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await noHorizontalOverflow(page);
    await login(page, "gp.vanapuram");
    for (const path of ["/dashboard", "/collection-points", "/collections", "/routes/planner", "/devices", "/analytics", "/demo"]) {
      await page.goto(path);
      await expect(page.locator("main h1").first()).toBeVisible();
      await page.waitForTimeout(400);
      await noHorizontalOverflow(page);
    }
  });
}

test("no critical or serious axe violations on key pages", async ({ page }) => {
  const report: Record<string, { critical: number; serious: number }> = {};
  await page.goto("/login");
  const scan = async (name: string) => {
    const r = await new AxeBuilder({ page }).analyze();
    report[name] = { critical: r.violations.filter((v) => v.impact === "critical").length, serious: r.violations.filter((v) => v.impact === "serious").length };
    for (const v of r.violations.filter((x) => x.impact === "critical" || x.impact === "serious")) {
      console.log(`[axe] ${name}: ${v.impact} ${v.id} (${v.nodes.length})`);
      for (const n of v.nodes.slice(0, 4)) console.log(`        ${n.target.join(" ")} :: ${(n.any[0]?.message ?? "").slice(0, 160)}`);
    }
  };
  await scan("login");
  await login(page, "gp.vanapuram");
  await page.goto("/dashboard");
  await expect(page.locator("main h1").first()).toBeVisible();
  await scan("dashboard");
  await page.goto("/collection-points");
  await expect(page.locator("main h1").first()).toBeVisible();
  await scan("collection-points");
  console.log("[axe] summary", JSON.stringify(report));
  for (const [name, r] of Object.entries(report)) {
    expect(r.critical, `${name}: critical`).toBe(0);
    expect(r.serious, `${name}: serious`).toBe(0);
  }
});
