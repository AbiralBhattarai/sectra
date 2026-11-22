import { clamp } from "./edlOps";
import type { AspectRatio, Crop, Edl, Facecam, Shot, Zoom } from "./types";

export interface SourceRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** The source rectangle (pixels) that becomes the output frame. The backend renderer
 * computes the same window for ffmpeg's crop filter. */
export function cropWindow(sourceWidth: number, sourceHeight: number, aspect: number, crop: Crop) {
  let width = sourceWidth;
  let height = sourceWidth / aspect;
  if (height > sourceHeight) {
    height = sourceHeight;
    width = sourceHeight * aspect;
  }
  width /= crop.scale;
  height /= crop.scale;
  return {
    x: clamp(crop.x * sourceWidth - width / 2, 0, sourceWidth - width),
    y: clamp(crop.y * sourceHeight - height / 2, 0, sourceHeight - height),
    width,
    height,
  };
}

/** CSS that shows exactly the source window `w` of a video inside its container. */
export function croppedVideoStyle(sourceWidth: number, sourceHeight: number, w: SourceRect) {
  return {
    width: `${(sourceWidth / w.width) * 100}%`,
    height: `${(sourceHeight / w.height) * 100}%`,
    left: `${(-w.x / w.width) * 100}%`,
    top: `${(-w.y / w.height) * 100}%`,
  };
}

/** Crop centre after dragging the picture by (dx, dy) frame pixels. */
export function panCrop(
  crop: Crop,
  dx: number,
  dy: number,
  frameWidth: number,
  frameHeight: number,
  sourceWidth: number,
  sourceHeight: number,
  aspect: number,
): Crop {
  const w = cropWindow(sourceWidth, sourceHeight, aspect, crop);
  // Re-derive the centre from the clamped window so dragging past an edge doesn't "stick".
  const centreX = (w.x + w.width / 2) / sourceWidth;
  const centreY = (w.y + w.height / 2) / sourceHeight;
  return {
    ...crop,
    x: clamp(centreX - (dx / frameWidth) * (w.width / sourceWidth), 0, 1),
    y: clamp(centreY - (dy / frameHeight) * (w.height / sourceHeight), 0, 1),
  };
}

/** Output frame sizes; the backend's `framing.OUTPUT_SIZES`. */
export const OUTPUT_SIZES: Record<AspectRatio, [number, number]> = {
  "9:16": [1080, 1920],
  "1:1": [1080, 1080],
  "16:9": [1920, 1080],
};

/** Streamer-mode box: 4:3, this share of the frame's shorter side wide, inset by MARGIN. */
const PIP_WIDTH = 0.4;
const PIP_RATIO = 4 / 3;
const PIP_MARGIN = 0.04;

/** The facecam box in output pixels: bottom right. The backend's `framing.pip_box`. */
export function pipBox(aspect: AspectRatio): SourceRect {
  const [outWidth, outHeight] = OUTPUT_SIZES[aspect];
  const short = Math.min(outWidth, outHeight);
  const width = Math.round((short * PIP_WIDTH) / 2) * 2;
  const height = Math.round(width / PIP_RATIO / 2) * 2;
  const margin = Math.round(short * PIP_MARGIN);
  return { x: outWidth - margin - width, y: outHeight - margin - height, width, height };
}

/** Source window shown in the facecam box. The backend's `framing.facecam_window`. */
export function facecamWindow(sourceWidth: number, sourceHeight: number, aspect: AspectRatio, facecam: Facecam) {
  const box = pipBox(aspect);
  return cropWindow(sourceWidth, sourceHeight, box.width / box.height, facecam);
}

/** Where streamer mode starts: the source's bottom-right corner, where most streamers'
 * cams sit. */
export const DEFAULT_FACECAM: Facecam = { x: 0.85, y: 0.85, scale: 3 };

export const streamerMode = (edl: Edl) => edl.facecam != null;

/** Face tracking drives the crop (never in streamer mode). */
export const trackingOn = (edl: Edl) => edl.tracking?.enabled === true && !streamerMode(edl);

/** The crop in effect at source time `t`: `edl.crop`, or with face tracking on, its zoom
 * centred where the last shot starting at or before `t` (else the first) points. The
 * backend's `framing.crop_at` is the same rule. */
export function cropAt(edl: Edl, t: number): Crop {
  if (!trackingOn(edl)) return edl.crop;
  const shot = edl.tracking!.shots[shotIndexAt(edl.tracking!.shots, t)];
  return { x: shot.x, y: shot.y, scale: edl.crop.scale };
}

/** `crop` applied at `t`: zoom is shared by every shot; with tracking on, the position
 * goes to the shot under `t` only. */
export function setCropAt(edl: Edl, t: number, crop: Crop): Edl {
  if (!trackingOn(edl)) return { ...edl, crop };
  const tracking = edl.tracking!;
  const index = shotIndexAt(tracking.shots, t);
  return {
    ...edl,
    crop: { ...edl.crop, scale: crop.scale },
    tracking: {
      ...tracking,
      shots: tracking.shots.map((s, i) => (i === index ? { ...s, x: crop.x, y: crop.y } : s)),
    },
  };
}

function shotIndexAt(shots: Shot[], t: number): number {
  let index = 0;
  for (let i = 1; i < shots.length && shots[i].start <= t; i++) index = i;
  return index;
}

/** Magnification at source time `t` from `edl.zooms` (1 outside them, and always with a
 * split screen): a punch-in holds its scale; a push eases in linearly over `ramp` seconds.
 * The backend's `framing.zoom_at` is the same rule. */
export function zoomAt(edl: Edl, t: number): number {
  if (edl.split_screen && !streamerMode(edl)) return 1;
  const zoom = edl.zooms.find((z) => z.start <= t && t < z.end);
  if (!zoom) return 1;
  if (zoom.ramp <= 0) return zoom.scale;
  return 1 + (zoom.scale - 1) * clamp((t - zoom.start) / zoom.ramp, 0, 1);
}

export const ZOOM_MIN_SECONDS = 0.2;

/** A new zoom at `t`, as long as `length` allows before the next zoom / the clip end;
 * null when there's no room. */
export function addZoom(edl: Edl, t: number, clipEnd: number, length = 1.5): Edl | null {
  if (edl.zooms.some((z) => z.start <= t && t < z.end)) return null;
  const next = edl.zooms.find((z) => z.start > t)?.start ?? clipEnd;
  const end = Math.min(t + length, next, clipEnd);
  if (end - t < ZOOM_MIN_SECONDS) return null;
  const zoom: Zoom = { start: round(t), end: round(end), scale: 1.2, ramp: 0 };
  return { ...edl, zooms: [...edl.zooms, zoom].sort((a, b) => a.start - b.start) };
}

/** Zoom `index` with `patch` applied, its times kept between its neighbours; unchanged
 * when that would leave it shorter than ZOOM_MIN_SECONDS. */
export function updateZoom(edl: Edl, index: number, patch: Partial<Zoom>): Edl {
  const zooms = edl.zooms;
  const low = index > 0 ? zooms[index - 1].end : 0;
  const high = index < zooms.length - 1 ? zooms[index + 1].start : Infinity;
  const next = { ...zooms[index], ...patch };
  next.start = round(clamp(next.start, low, high));
  next.end = round(clamp(next.end, low, high));
  next.scale = clamp(next.scale, 1, 2);
  next.ramp = Math.max(0, next.ramp);
  if (next.end - next.start < ZOOM_MIN_SECONDS) return edl;
  return { ...edl, zooms: zooms.map((z, i) => (i === index ? next : z)) };
}

const round = (t: number) => Math.round(t * 1000) / 1000;
