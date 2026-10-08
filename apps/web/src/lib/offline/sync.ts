/**
 * Offline queue + synchronisation engine.
 *
 * Guarantees (together with the idempotent POST /sync/batch):
 *  - records are written to IndexedDB before any network call, so a refresh or crash never loses them;
 *  - every record keeps one immutable event_id, so retries can never create duplicates on the server;
 *  - transport failures keep the record "queued" with exponential backoff; only server rejections become "failed";
 *  - a record is marked "synced" only after the server acknowledges that exact event_id.
 * Background sync is not assumed: syncing runs while the app is open (on start, on reconnect, every 30 s, or manually).
 */
import { ApiError, NetworkError, api } from "@/lib/api";
import type { CollectionPayload, SyncResult } from "@/lib/types";
import { uuidv4 } from "@/lib/utils";
import { type QueuedEvent, getDb } from "./db";

const BATCH_SIZE = 25;
const MAX_BACKOFF_MS = 5 * 60_000;

export function backoffMs(attempts: number, random: () => number = Math.random): number {
  const base = Math.min(MAX_BACKOFF_MS, 2_000 * 2 ** Math.min(attempts, 12));
  return Math.round(base * (0.8 + 0.4 * random()));
}

export function clientId(): string {
  try {
    let id = localStorage.getItem("pl_client_id");
    if (!id) {
      id = uuidv4();
      localStorage.setItem("pl_client_id", id);
    }
    return id;
  } catch {
    return "unknown-device";
  }
}

export interface NewCollection {
  userId: string;
  payload: CollectionPayload;
  photo?: Blob | null;
  pointLabel: string;
  streamLabel: string;
  draft?: boolean;
}

export async function enqueueCollection(input: NewCollection): Promise<QueuedEvent> {
  const db = getDb();
  const now = Date.now();
  const photoId = input.photo ? uuidv4() : null;
  const event: QueuedEvent = {
    event_id: uuidv4(),
    user_id: input.userId,
    type: "collection",
    status: input.draft ? "draft" : "queued",
    payload: { ...input.payload, media_id: null },
    photo_id: photoId,
    client_created_at: new Date(now).toISOString(),
    created_at: now,
    updated_at: now,
    attempts: 0,
    next_attempt_at: now,
    last_error: null,
    point_label: input.pointLabel,
    stream_label: input.streamLabel,
  };
  await db.transaction("rw", db.events, db.photos, async () => {
    if (photoId && input.photo) await db.photos.put({ id: photoId, blob: input.photo, created_at: now });
    await db.events.put(event);
  });
  return event;
}

/** Drafts are edited in place. A server-rejected record is corrected into a NEW event (new immutable id). */
export async function editQueued(eventId: string, patch: Partial<CollectionPayload>, submit: boolean): Promise<string> {
  const db = getDb();
  const ev = await db.events.get(eventId);
  if (!ev) throw new Error("Record not found");
  const now = Date.now();
  if (ev.status === "draft") {
    await db.events.update(eventId, {
      payload: { ...ev.payload, ...patch },
      status: submit ? "queued" : "draft",
      updated_at: now,
      next_attempt_at: now,
    });
    return eventId;
  }
  if (ev.status === "failed") {
    const fresh: QueuedEvent = {
      ...ev,
      event_id: uuidv4(),
      payload: { ...ev.payload, ...patch },
      status: submit ? "queued" : "draft",
      attempts: 0,
      next_attempt_at: now,
      last_error: null,
      replaces: ev.event_id,
      client_created_at: new Date(now).toISOString(),
      created_at: now,
      updated_at: now,
    };
    await db.transaction("rw", db.events, async () => {
      await db.events.put(fresh);
      await db.events.delete(ev.event_id);
    });
    return fresh.event_id;
  }
  throw new Error("Only drafts and rejected records can be edited");
}

export async function discardQueued(eventId: string) {
  const db = getDb();
  const ev = await db.events.get(eventId);
  if (!ev || !["draft", "failed"].includes(ev.status)) throw new Error("Only drafts and rejected records can be discarded");
  await db.transaction("rw", db.events, db.photos, async () => {
    if (ev.photo_id) await db.photos.delete(ev.photo_id);
    await db.events.delete(eventId);
  });
}

export async function acknowledgeConflict(eventId: string) {
  // The server kept its original version; the admin resolves it there. Locally we just stop showing it as pending.
  await getDb().events.update(eventId, { status: "synced", updated_at: Date.now() });
}

export interface SyncSummary {
  attempted: number;
  synced: number;
  conflicts: number;
  failed: number;
  deferred: number;
  offline: boolean;
  authRequired: boolean;
}

let running: Promise<SyncSummary> | null = null;

export function syncNow(userId: string, opts: { force?: boolean } = {}): Promise<SyncSummary> {
  if (!running) running = run(userId, !!opts.force).finally(() => (running = null));
  return running;
}

const messageOf = (err: unknown) => (err instanceof Error ? err.message : "Unknown error");

async function defer(ev: QueuedEvent, message: string, countAttempt = true) {
  const attempts = ev.attempts + (countAttempt ? 1 : 0);
  await getDb().events.update(ev.event_id, {
    status: "queued",
    attempts,
    next_attempt_at: Date.now() + backoffMs(attempts),
    last_error: { code: "RETRY_SCHEDULED", message },
    updated_at: Date.now(),
  });
}

async function uploadPhoto(ev: QueuedEvent): Promise<string | null> {
  const photo = ev.photo_id ? await getDb().photos.get(ev.photo_id) : undefined;
  if (!photo) return null; // storage was cleared: keep the collection, drop the missing photo
  const form = new FormData();
  form.append("file", photo.blob, "collection.jpg");
  form.append("purpose", "collection_photo");
  const media = await api<{ id: string }>("/media", { method: "POST", form });
  return media.id;
}

async function run(userId: string, force: boolean): Promise<SyncSummary> {
  const db = getDb();
  const summary: SyncSummary = { attempted: 0, synced: 0, conflicts: 0, failed: 0, deferred: 0, offline: false, authRequired: false };
  const now = Date.now();
  const due = (
    await db.events
      .where("user_id")
      .equals(userId)
      .filter((e) => (e.status === "queued" || e.status === "syncing") && (force || e.next_attempt_at <= now))
      .toArray()
  ).sort((a, b) => a.created_at - b.created_at);

  for (let i = 0; i < due.length; i += BATCH_SIZE) {
    const ready: QueuedEvent[] = [];
    for (const ev of due.slice(i, i + BATCH_SIZE)) {
      if (ev.photo_id && !ev.payload.media_id) {
        try {
          const mediaId = await uploadPhoto(ev);
          const oldPhoto = ev.photo_id;
          ev.payload = { ...ev.payload, media_id: mediaId };
          ev.photo_id = null;
          await db.events.put(ev);
          await db.photos.delete(oldPhoto);
        } catch (err) {
          if (err instanceof ApiError && err.status === 401) {
            summary.authRequired = true;
            return summary;
          }
          if (err instanceof NetworkError || (err instanceof ApiError && err.status >= 500)) {
            await defer(ev, messageOf(err));
            summary.offline = true;
            summary.deferred++;
            continue;
          }
          await db.events.update(ev.event_id, {
            status: "failed",
            last_error: { code: err instanceof ApiError ? err.code : "PHOTO_FAILED", message: messageOf(err) },
            updated_at: Date.now(),
          });
          summary.failed++;
          continue;
        }
      }
      ready.push(ev);
    }
    if (!ready.length) {
      if (summary.offline) break;
      continue;
    }

    await db.events.bulkPut(ready.map((e) => ({ ...e, status: "syncing" as const, updated_at: Date.now() })));
    summary.attempted += ready.length;
    let results: SyncResult[];
    try {
      const res = await api<{ results: SyncResult[] }>("/sync/batch", {
        method: "POST",
        body: {
          client_id: clientId(),
          events: ready.map((e) => ({ event_id: e.event_id, type: e.type, client_created_at: e.client_created_at, payload: e.payload })),
        },
      });
      results = res.results;
    } catch (err) {
      const auth = err instanceof ApiError && err.status === 401;
      summary.offline = err instanceof NetworkError || (err instanceof ApiError && err.status >= 500);
      summary.authRequired = auth;
      for (const e of ready) await defer(e, messageOf(err), !auth);
      summary.deferred += ready.length;
      break;
    }

    const byId = new Map(results.map((r) => [r.event_id, r]));
    for (const e of ready) {
      const r = byId.get(e.event_id);
      if (!r) {
        await defer(e, "No acknowledgement received"); // never assume success
        summary.deferred++;
      } else if (r.status === "accepted" || r.status === "duplicate") {
        await db.events.update(e.event_id, {
          status: "synced",
          server_id: r.server_id ?? e.event_id,
          review_status: r.review_status ?? null,
          last_error: null,
          updated_at: Date.now(),
        });
        summary.synced++;
      } else if (r.status === "conflict") {
        await db.events.update(e.event_id, { status: "conflict", last_error: { code: r.code, message: r.message ?? "" }, updated_at: Date.now() });
        summary.conflicts++;
      } else {
        await db.events.update(e.event_id, { status: "failed", last_error: { code: r.code, message: r.message ?? "" }, updated_at: Date.now() });
        summary.failed++;
      }
    }
  }
  return summary;
}

/** Shrinks camera photos before storing them offline (phones produce 3–8 MB images). */
export async function compressImage(file: Blob, maxSide = 1280, quality = 0.8): Promise<Blob> {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    return await new Promise<Blob>((resolve) => canvas.toBlob((b) => resolve(b ?? file), "image/jpeg", quality));
  } catch {
    return file;
  }
}
