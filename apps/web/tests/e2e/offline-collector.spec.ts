import { expect, test } from "@playwright/test";
import { apiToken, login } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

test("collector records a collection offline, survives a reload, and it syncs exactly once", async ({ page, context, request }) => {
  // Unique per run (so the server check is unambiguous); two decimals without a trailing zero, as the UI displays it.
  const weight = `7.${Math.floor(Math.random() * 9)}${Math.floor(Math.random() * 9) + 1}`;

  // 1-3. Online once: sign in, open the collector app, let it cache today's stops and install the service worker.
  await login(page, "collector1");
  await page.goto("/collector");
  await expect(page.getByText(/Stops saved/)).toBeVisible();
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  await page.reload();
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
  await expect(page.getByText(/Stops saved/)).toBeVisible();

  // 4. Lose the network.
  await context.setOffline(true);
  await expect(page.getByText("Offline: saving on this phone").first()).toBeVisible();

  // 5-6. Record a collection at the first stop; it is stored on the phone.
  await page.locator("ul li button").filter({ hasText: /CP-/ }).first().click();
  await page.locator("#weight").fill(weight);
  await page.getByRole("button", { name: /Save on phone|Save collection/ }).click();
  await expect(page.getByText("1 on this phone not yet synced")).toBeVisible();

  // 7. Reload while offline: the service worker serves the app, IndexedDB still holds the record.
  await page.reload();
  await expect(page.getByText("1 on this phone not yet synced")).toBeVisible();
  await page.goto("/collector/offline-queue");
  await expect(page.getByText(`${weight} kg`).first()).toBeVisible();

  // 8-9. Back online: sync.
  await context.setOffline(false);
  await page.goto("/collector");
  await page.getByRole("button", { name: "Sync now" }).click();
  await expect(page.getByText("0 on this phone not yet synced")).toBeVisible({ timeout: 30_000 });

  // 10. Syncing again must not create a second row.
  await page.getByRole("button", { name: "Sync now" }).click();
  await page.waitForTimeout(1500);

  // 11. The server holds exactly one event with this weight.
  const token = await apiToken(request, "collector1");
  const r = await request.get("/api/v1/collections", { params: { mine: true, page_size: 50, sort: "-collected_at" }, headers: { Authorization: `Bearer ${token}` } });
  expect(r.ok(), await r.text()).toBeTruthy();
  const items = (await r.json()).items as { weight_kg: number; offline_captured: boolean }[];
  const matches = items.filter((e) => e.weight_kg === Number(weight));
  expect(matches).toHaveLength(1);
  expect(matches[0].offline_captured).toBe(true);
});
