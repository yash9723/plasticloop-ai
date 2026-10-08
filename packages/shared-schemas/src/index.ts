// Generated contract types (see api.d.ts, produced by `pnpm gen:api` from apps/api/openapi.json).
export type { components, operations, paths } from "./api";
import type { components } from "./api";

export type Schemas = components["schemas"];
export type Schema<K extends keyof Schemas> = Schemas[K];
