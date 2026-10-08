import Dexie, { type Table } from "dexie";
import type { CollectionPayload, MyTasks } from "@/lib/types";

export type QueueStatus = "draft" | "queued" | "syncing" | "synced" | "conflict" | "failed";

/** One offline collection. `event_id` is generated on the phone and never changes (server idempotency key). */
export interface QueuedEvent {
  event_id: string;
  user_id: string;
  type: "collection";
  status: QueueStatus;
  payload: CollectionPayload;
  photo_id?: string | null;
  client_created_at: string;
  created_at: number;
  updated_at: number;
  attempts: number;
  next_attempt_at: number;
  last_error?: { code?: string | null; message: string } | null;
  server_id?: string | null;
  review_status?: string | null;
  point_label: string;
  stream_label: string;
  replaces?: string | null;
}

export interface CachedTasks {
  user_id: string;
  data: MyTasks;
  cached_at: number;
}

export interface StoredPhoto {
  id: string;
  blob: Blob;
  created_at: number;
}

class PlasticLoopDB extends Dexie {
  events!: Table<QueuedEvent, string>;
  tasks!: Table<CachedTasks, string>;
  photos!: Table<StoredPhoto, string>;

  constructor() {
    super("plasticloop");
    this.version(1).stores({
      events: "event_id, status, user_id, created_at",
      tasks: "user_id",
      photos: "id",
    });
  }
}

let instance: PlasticLoopDB | null = null;

/** Lazily opened so server rendering never touches IndexedDB. */
export function getDb(): PlasticLoopDB {
  if (!instance) instance = new PlasticLoopDB();
  return instance;
}

export async function countPending(userId: string): Promise<number> {
  return getDb()
    .events.where("user_id")
    .equals(userId)
    .filter((e) => e.status !== "synced")
    .count();
}

export async function cacheTasks(userId: string, data: MyTasks) {
  await getDb().tasks.put({ user_id: userId, data, cached_at: Date.now() });
}

export async function getCachedTasks(userId: string): Promise<CachedTasks | undefined> {
  return getDb().tasks.get(userId);
}

/** QR lookup against the cached point list, so scanning works with no network. */
export async function findPointByQr(userId: string, raw: string) {
  const code = raw.replace(/^plasticloop:cp:/i, "").trim().toUpperCase();
  const cached = await getCachedTasks(userId);
  return cached?.data.points.find((p) => p.qr_code === code || p.code.toUpperCase() === code) ?? null;
}
