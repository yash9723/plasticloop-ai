import { type APIRequestContext, expect, type Page } from "@playwright/test";

export const PASSWORD = "PlasticLoop@2026"; // development-only demo password from the seed script
export const email = (local: string) => `${local}@plasticloop.example`;

export async function login(page: Page, local: string) {
  await page.goto("/login");
  await page.getByLabel("Email or phone").fill(email(local));
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login/, { timeout: 20_000 });
}

export async function apiToken(request: APIRequestContext, local: string): Promise<string> {
  const r = await request.post("/api/v1/auth/login", { data: { identifier: email(local), password: PASSWORD } });
  expect(r.ok()).toBeTruthy();
  return (await r.json()).access_token;
}

export async function noHorizontalOverflow(page: Page) {
  const { doc, inner } = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth, inner: window.innerWidth }));
  expect(doc, `page is ${doc}px wide in a ${inner}px viewport`).toBeLessThanOrEqual(inner);
}
