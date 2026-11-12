import type { SourceRect } from "../crop";

/** DOM elements the playback engine drives, registered by the layers that render them. */
export const slotVideos: (HTMLVideoElement | null)[] = [null, null];
/** Split screen: the canvas showing a slot's right half, and the source rect to copy. */
export const slotCanvases: (HTMLCanvasElement | null)[] = [null, null];
export const slotRightRects: (SourceRect | null)[] = [null, null];
export const brollVideos = new Map<string, HTMLVideoElement>();
