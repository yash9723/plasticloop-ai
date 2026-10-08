"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { refreshSession } from "@/lib/api";
import { useAuth } from "@/lib/auth-store";
import { backoffMs } from "@/lib/offline/sync";

/** Query-key prefixes refreshed when the server announces a change of the given kind. */
const AFFECTS: Record<string, string[]> = {
  telemetry: ["/devices", "/collection-points", "/notifications", "/analytics"],
  device_status: ["/devices", "/notifications"],
};

/**
 * Subscribes to /api/v1/events/stream (server-sent events read with fetch so the token stays in a header, not the URL)
 * and invalidates affected TanStack queries. Reconnects with backoff; pages still work without it, just less live.
 */
export function useLiveEvents() {
  const qc = useQueryClient();
  const token = useAuth((s) => s.accessToken);
  useEffect(() => {
    if (!token) return;
    const ctrl = new AbortController();
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const invalidate = (kind: string) => {
      const prefixes = AFFECTS[kind];
      if (!prefixes) return;
      qc.invalidateQueries({ predicate: (q) => typeof q.queryKey[0] === "string" && prefixes.some((p) => (q.queryKey[0] as string).startsWith(p)) });
    };

    const connect = async () => {
      try {
        const res = await fetch("/api/v1/events/stream", { headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" }, signal: ctrl.signal });
        if (res.status === 401) {
          await refreshSession(); // new token re-runs this effect
          return;
        }
        if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
        attempt = 0;
        const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
        let buf = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += value;
          let sep: number;
          while ((sep = buf.indexOf("\n\n")) >= 0) {
            const block = buf.slice(0, sep);
            buf = buf.slice(sep + 2);
            const event = /^event: (.+)$/m.exec(block)?.[1];
            if (event) invalidate(event);
          }
        }
      } catch {
        if (ctrl.signal.aborted) return;
      }
      if (!ctrl.signal.aborted) timer = setTimeout(connect, backoffMs(attempt++));
    };
    void connect();
    return () => {
      ctrl.abort();
      clearTimeout(timer);
    };
  }, [token, qc]);
}
