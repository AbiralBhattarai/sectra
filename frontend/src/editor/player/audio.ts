import { useEditor } from "../store";

/** Directly drive native HTMLMediaElement volume and mute state.
 * Routing through Web Audio's createMediaElementSource breaks hardware AV
 * synchronization in Chromium/WebKit and introduces a 100-250ms lip-sync delay. */
export function setGain(element: HTMLMediaElement, value: number): void {
  const v = Math.min(1, Math.max(0, value));
  if (v === 0) {
    if (!element.muted) element.muted = true;
    if (element.volume !== 0) element.volume = 0;
  } else {
    if (element.muted) element.muted = false;
    if (Math.abs(element.volume - v) > 0.01) element.volume = v;
  }
}

/** Play/pause from a user gesture (button, key). */
export function togglePlayback(): void {
  useEditor.getState().togglePlay();
}
