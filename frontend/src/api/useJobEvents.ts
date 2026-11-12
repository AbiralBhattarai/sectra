import { useEffect, useRef } from "react";
import type { ClipEvent, JobEvent } from "./types";

type Listeners = { job: Set<(event: JobEvent) => void>; clip: Set<(event: ClipEvent) => void> };

const listeners: Listeners = { job: new Set(), clip: new Set() };
let source: EventSource | null = null;

/** One /api/events connection shared by every subscriber; closed when the last leaves. */
function subscribe<K extends keyof Listeners>(kind: K, handler: Parameters<Listeners[K]["add"]>[0]) {
  (listeners[kind] as Set<typeof handler>).add(handler);
  if (!source) {
    // EventSource reconnects on its own after a dropped connection.
    source = new EventSource("/api/events");
    for (const name of ["job", "clip"] as const) {
      source.addEventListener(name, (message) => {
        const data = JSON.parse((message as MessageEvent<string>).data);
        for (const listener of listeners[name]) (listener as (event: unknown) => void)(data);
      });
    }
  }
  return () => {
    (listeners[kind] as Set<typeof handler>).delete(handler);
    if (!listeners.job.size && !listeners.clip.size) {
      source?.close();
      source = null;
    }
  };
}

/** Calls `onEvent` for every job event from the /api/events SSE stream. */
export function useJobEvents(onEvent: (event: JobEvent) => void): void {
  const handler = useRef(onEvent);
  handler.current = onEvent;
  useEffect(() => subscribe("job", (event: JobEvent) => handler.current(event)), []);
}

/** Calls `onEvent` whenever a clip's EDL changes on the server. */
export function useClipEvents(onEvent: (event: ClipEvent) => void): void {
  const handler = useRef(onEvent);
  handler.current = onEvent;
  useEffect(() => subscribe("clip", (event: ClipEvent) => handler.current(event)), []);
}
