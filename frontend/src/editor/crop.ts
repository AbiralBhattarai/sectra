import { clamp } from "./edlOps";
import type { Crop, Edl, Shot } from "./types";

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

export const trackingOn = (edl: Edl) => edl.tracking?.enabled === true;

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
