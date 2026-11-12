import { useClipEvents } from "../api/useJobEvents";
import { editing, reload } from "./commands";
import { useEditor } from "./store";

/** Picks up edits made elsewhere — an LLM over MCP, face tracking, another tab — by
 * reloading the clip when the server announces a newer revision. */
export function useClipSync(): void {
  useClipEvents((event) => {
    const { clip, revision } = useEditor.getState();
    if (!clip || event.clip_id !== clip.id || event.revision === revision) return;
    // This editor's own edit: its response is on the way.
    if (event.actor === "editor" && editing()) return;
    void reload(clip.id);
  });
}
