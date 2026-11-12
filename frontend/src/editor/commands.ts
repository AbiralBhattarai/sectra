import { ApiError, applyEdits, getClip, redoClip, undoClip } from "../api/client";
import type { ClipDetail, EditCommand } from "./types";
import { useEditor } from "./store";

/** Every edit is a list of commands the server applies as one revision (the same API an
 * MCP server will use). Requests go one at a time, each against the revision the last
 * one produced, so quick edits never race each other. */

let queue: Promise<unknown> = Promise.resolve();
let inFlight = 0;

function enqueue(work: (clipId: string) => Promise<ClipDetail>): Promise<boolean> {
  const result = queue.then(async () => {
    const { clip, setClip, setSaveState } = useEditor.getState();
    if (!clip) return false;
    inFlight++;
    setSaveState("saving");
    try {
      const saved = await work(clip.id);
      if (useEditor.getState().clip?.id === clip.id) {
        setClip(saved);
        setSaveState("saved");
      }
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        await reload(clip.id);
        setSaveState("error", "The clip changed elsewhere, so it was reloaded. Try again.");
      } else {
        setSaveState("error", (e as Error).message);
      }
      return false;
    } finally {
      inFlight--;
    }
  });
  queue = result.catch(() => undefined);
  return result;
}

/** Apply commands; resolves false (with the error shown in the toolbar) when rejected. */
export function run(...commands: EditCommand[]): Promise<boolean> {
  if (!commands.length) return Promise.resolve(true);
  return enqueue((clipId) => applyEdits(clipId, commands, useEditor.getState().revision));
}

export const undo = () => enqueue(undoClip);
export const redo = () => enqueue(redoClip);

/** Fetch the clip again (someone else — an LLM, face tracking — changed it). */
export async function reload(clipId: string): Promise<void> {
  const clip = await getClip(clipId);
  if (useEditor.getState().clip?.id === clipId) useEditor.getState().setClip(clip);
}

/** Whether one of this editor's own requests is waiting for its answer. */
export const editing = () => inFlight > 0;
