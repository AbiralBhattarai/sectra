import { useEffect, useRef } from "react";
import type { JobEvent } from "./types";

/** Calls `onEvent` for every job event from the /api/events SSE stream. */
export function useJobEvents(onEvent: (event: JobEvent) => void): void {
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    // EventSource reconnects on its own after a dropped connection.
    const source = new EventSource("/api/events");
    source.addEventListener("job", (message) => {
      handler.current(JSON.parse((message as MessageEvent<string>).data));
    });
    return () => source.close();
  }, []);
}
