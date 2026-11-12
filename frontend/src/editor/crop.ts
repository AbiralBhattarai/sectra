import { clamp, isClipVideo, mediaTime, type Placed } from "./sequence";
import type { Crop, Edl, EditCommand, Segment, Shot } from "./types";

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

/** Face tracking frames clip-video segments that have no crop of their own. */
export const followsTracking = (edl: Edl, segment: Segment) =>
  trackingOn(edl) && isClipVideo(segment) && segment.crop === null;

/** Split screen applies to clip-video segments; face tracking wins over it. */
export const splitApplies = (edl: Edl, segment: Segment) =>
  edl.split_screen && !trackingOn(edl) && isClipVideo(segment);

/** How far (0..1) media time `t` is through the segment. */
export function progress(segment: Segment, t: number): number {
  if (segment.kind === "video") return clamp((t - segment.start) / (segment.end - segment.start), 0, 1);
  if (segment.kind === "image") return clamp(t / segment.duration, 0, 1);
  return 0;
}

/** The crop in effect at media time `t` of `segment`: its own crop (animated towards
 * `crop_to` — Ken Burns), else with face tracking the shot starting at or before `t`
 * (else the first) at the shared zoom, else `edl.crop`. The backend's
 * `framing.crop_at` is the same rule. */
export function cropAt(edl: Edl, segment: Segment, t: number): Crop {
  if (segment.crop) {
    const target = segment.kind === "freeze" ? null : segment.crop_to;
    if (!target) return segment.crop;
    const p = progress(segment, t);
    const a = segment.crop;
    return { x: a.x + (target.x - a.x) * p, y: a.y + (target.y - a.y) * p, scale: a.scale + (target.scale - a.scale) * p };
  }
  if (followsTracking(edl, segment)) {
    const shot = edl.tracking!.shots[shotIndexAt(edl.tracking!.shots, t)];
    return { x: shot.x, y: shot.y, scale: edl.crop.scale };
  }
  return edl.crop;
}

/** The commands that apply `crop` (dragged or zoomed in the preview at output time `t`):
 * to the segment's own framing (its Ken Burns end once past the middle), to the face-
 * tracking shot under `t` (zoom is shared), or to the clip's framing. */
export function reframeCommands(edl: Edl, p: Placed, t: number, crop: Crop): EditCommand[] {
  const segment = p.segment;
  const at = mediaTime(p, t);
  if (segment.crop) {
    const toEnd = segment.kind !== "freeze" && segment.crop_to && progress(segment, at) >= 0.5;
    return [{ op: "update_segment", segment_ids: [segment.id], ...(toEnd ? { crop_to: crop } : { crop }) }];
  }
  if (followsTracking(edl, segment)) {
    const commands: EditCommand[] = [
      { op: "reframe_shot", index: shotIndexAt(edl.tracking!.shots, at), x: crop.x, y: crop.y },
    ];
    if (crop.scale !== edl.crop.scale) commands.push({ op: "update_clip", crop: { ...edl.crop, scale: crop.scale } });
    return commands;
  }
  return [{ op: "update_clip", crop }];
}

export function shotIndexAt(shots: Shot[], t: number): number {
  let index = 0;
  for (let i = 1; i < shots.length && shots[i].start <= t; i++) index = i;
  return index;
}
