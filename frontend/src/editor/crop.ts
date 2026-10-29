import { clamp } from "./edlOps";
import type { Crop } from "./types";

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

/** CSS that shows exactly the crop window of a video inside a frame of the target aspect. */
export function croppedVideoStyle(sourceWidth: number, sourceHeight: number, aspect: number, crop: Crop) {
  const w = cropWindow(sourceWidth, sourceHeight, aspect, crop);
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
