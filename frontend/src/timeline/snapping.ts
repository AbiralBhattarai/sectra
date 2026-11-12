import { layout } from "../editor/sequence";
import type { Edl } from "../editor/types";

/** Snap within this many pixels. */
export const SNAP_PIXELS = 8;

/** Times worth snapping to: the clip's ends, cuts, the playhead, markers and the edges
 * of overlays and B-roll — except the dragged item's own (`ignore` ids). */
export function snapTargets(edl: Edl, playhead: number, ignore: string[] = []): number[] {
  const placed = layout(edl.segments);
  const end = placed.length ? placed[placed.length - 1].end : 0;
  const times = [0, end, playhead, ...edl.markers.map((m) => m.time)];
  for (const p of placed.slice(1)) if (!ignore.includes(p.segment.id)) times.push(p.ownStart);
  for (const o of edl.overlays) if (!ignore.includes(o.id)) times.push(o.start, o.end);
  for (const b of edl.broll) if (!ignore.includes(b.id)) times.push(b.start, b.start + b.duration);
  return times;
}

/** `t`, moved onto the nearest target within `SNAP_PIXELS` at `pxPerSecond`. */
export function snap(t: number, targets: number[], pxPerSecond: number): number {
  let best = t;
  let distance = SNAP_PIXELS / pxPerSecond;
  for (const target of targets) {
    const d = Math.abs(target - t);
    if (d < distance) {
      best = target;
      distance = d;
    }
  }
  return best;
}
