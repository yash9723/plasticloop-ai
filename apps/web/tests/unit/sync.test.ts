import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getDb } from "@/lib/offline/db";
import { backoffMs, editQueued, enqueueCollection, syncNow } from "@/lib/offline/sync";

const USER = "user-1";
const payload = {
  collection_point_id: "11111111-1111-4111-8111-111111111111",
  waste_stream_id: "22222222-2222-4222-8222-222222222222",
  weight_kg: "2.500",
  measurement_source: "manual_entry",
  collected_at: "2026-10-08T07:30:00+05:30",
} as never;

type Result = { status: string; code?: string; message?: string };
let respond: (ids: string[]) => Result[] | Error;
const calls: string[][] = [];

function stubFetch() {
  vi.stubGlobal("fetch", vi.fn(async (_url: string, init: RequestInit) => {
    const ids = (JSON.parse(String(init.body)).events as { event_id: string }[]).map((e) => e.event_id);
    calls.push(ids);
    const out = respond(ids);
    if (out instanceof Error) throw out;
    return new Response(JSON.stringify({ results: ids.map((id, i) => ({ event_id: id, ...out[i] })) }), {
      status: 200, headers: { "content-type": "application/json" },
    });
  }));
}

const add = () => enqueueCollection({ userId: USER, payload, pointLabel: "CP-1", streamLabel: "Rigid" });
const get = (id: string) => getDb().events.get(id);

beforeEach(async () => {
  calls.length = 0;
  await getDb().events.clear();
  stubFetch();
});
afterEach(() => vi.unstubAllGlobals());

describe("backoff", () => {
  it("grows exponentially with jitter and is capped at 5 minutes", () => {
    expect(backoffMs(0, () => 0.5)).toBe(2000);
    expect(backoffMs(3, () => 0.5)).toBe(16000);
    expect(backoffMs(50, () => 1)).toBe(Math.round(300000 * 1.2));
    expect(backoffMs(1, () => 0)).toBe(3200);
  });
});

describe("offline queue", () => {
  it("stores the record locally before any network call", async () => {
    const ev = await add();
    expect(calls).toHaveLength(0);
    expect((await get(ev.event_id))?.status).toBe("queued");
  });

  it("marks accepted and duplicate records as synced", async () => {
    const a = await add();
    const b = await add();
    respond = () => [{ status: "accepted" }, { status: "duplicate" }];
    const s = await syncNow(USER);
    expect(s.synced).toBe(2);
    expect((await get(a.event_id))?.status).toBe("synced");
    expect((await get(b.event_id))?.status).toBe("synced");
  });

  it("keeps records queued with backoff when the network fails, then sends the same event id again", async () => {
    const ev = await add();
    respond = () => new TypeError("Failed to fetch");
    const s = await syncNow(USER);
    expect(s.offline).toBe(true);
    const after = await get(ev.event_id);
    expect(after?.status).toBe("queued");
    expect(after?.attempts).toBe(1);
    expect(after!.next_attempt_at).toBeGreaterThan(Date.now());
    expect(await syncNow(USER)).toMatchObject({ attempted: 0 }); // not due yet
    respond = () => [{ status: "accepted" }];
    await syncNow(USER, { force: true });
    expect(calls[1]).toEqual([ev.event_id]); // same immutable id → server can deduplicate
    expect((await get(ev.event_id))?.status).toBe("synced");
  });

  it("never assumes success without an acknowledgement", async () => {
    const ev = await add();
    respond = () => [];
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ results: [] }), { status: 200, headers: { "content-type": "application/json" } })));
    const s = await syncNow(USER);
    expect(s.deferred).toBe(1);
    expect((await get(ev.event_id))?.status).toBe("queued");
  });

  it("records conflicts and rejections separately", async () => {
    const a = await add();
    const b = await add();
    respond = () => [{ status: "conflict", code: "PAYLOAD_MISMATCH", message: "x" }, { status: "rejected", code: "WEIGHT_OUT_OF_RANGE", message: "too heavy" }];
    const s = await syncNow(USER);
    expect(s).toMatchObject({ conflicts: 1, failed: 1 });
    expect((await get(a.event_id))?.status).toBe("conflict");
    expect((await get(b.event_id))?.last_error?.code).toBe("WEIGHT_OUT_OF_RANGE");
  });

  it("corrects a rejected record into a new event that references the old one", async () => {
    const ev = await add();
    respond = () => [{ status: "rejected", code: "WEIGHT_OUT_OF_RANGE", message: "too heavy" }];
    await syncNow(USER);
    const newId = await editQueued(ev.event_id, { weight_kg: "1.200" } as never, true);
    expect(newId).not.toBe(ev.event_id);
    expect(await get(ev.event_id)).toBeUndefined();
    const fresh = await get(newId);
    expect(fresh?.replaces).toBe(ev.event_id);
    expect(fresh?.status).toBe("queued");
  });
});
