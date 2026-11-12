import type { CSSProperties } from "react";
import { imageUrl, mediaUrl } from "../../api/client";
import { cropAt, croppedVideoStyle, cropWindow, splitApplies } from "../crop";
import { mediaTime, type Placed } from "../sequence";
import { useEditor } from "../store";
import { ASPECTS, type Crop, type Segment } from "../types";
import { slotCanvases, slotRightRects, slotVideos } from "./elements";
import { colorFilter, transitionLook, transitionProgress, type SlotTarget } from "./playback";

interface Props {
  slot: number;
  target: SlotTarget | null;
  /** The segment entering after this one, while it transitions in. */
  next: Placed | null;
  frame: { width: number; height: number };
  /** Framing being dragged in the preview (for the segment under the playhead). */
  draftCrop: Crop | null;
}

/** One of the two main-track players: a video (or image) cropped like the render, graded
 * with a CSS filter and styled for any transition it is part of. */
export function SegmentLayer({ slot, target, next, frame, draftCrop }: Props) {
  const edl = useEditor((s) => s.edl)!;
  const video = useEditor((s) => s.video)!;
  const playhead = useEditor((s) => s.playhead);
  const mediaSizes = useEditor((s) => s.mediaSizes);
  const noteMediaSize = useEditor((s) => s.noteMediaSize);

  const p = target?.placed ?? null;
  const segment: Segment | null = p?.segment ?? null;
  const key = segment ? mediaKey(segment, video.id) : null;
  const size = (key && mediaSizes[key]) || { width: 1920, height: 1080 };
  const t = p && target?.active ? mediaTime(p, playhead) : p ? mediaTime(p, p.start) : 0;

  const aspect = ASPECTS[edl.aspect];
  const split = !!segment && splitApplies(edl, segment);
  const pane = split
    ? { height: frame.height / 2, sourceWidth: size.width / 2, aspect: aspect * 2 }
    : { height: frame.height, sourceWidth: size.width, aspect };
  const crop = draftCrop ?? (segment ? cropAt(edl, segment, t) : edl.crop);
  const rect = cropWindow(pane.sourceWidth, size.height, pane.aspect, crop);
  slotRightRects[slot] = split ? { ...rect, x: rect.x + pane.sourceWidth } : null;

  let look: CSSProperties = {};
  if (p && segment && target?.active) {
    const q = transitionProgress(edl.segments, p, playhead);
    if (q != null && segment.transition) look = transitionLook(segment.transition.type, q).incoming;
    if (next?.segment.transition) {
      const qNext = transitionProgress(edl.segments, next, playhead);
      if (qNext != null) look = { ...look, ...transitionLook(next.segment.transition.type, qNext).outgoing };
    }
  }
  const style: CSSProperties = {
    visibility: target?.active ? "visible" : "hidden",
    zIndex: p ? p.index + 1 : 0,
    filter: segment ? colorFilter(segment.color) : undefined,
    ...look,
  };
  const src =
    segment && segment.kind !== "image" ? mediaUrl(segment.media ?? video.id, "source.mp4") : undefined;

  return (
    <div className="segment-layer" style={style}>
      <div className="pane" style={{ height: pane.height }}>
        <video
          ref={(element) => {
            slotVideos[slot] = element;
          }}
          src={src}
          style={{ ...croppedVideoStyle(size.width, size.height, rect), display: segment?.kind === "image" ? "none" : undefined }}
          preload="auto"
          playsInline
          onLoadedMetadata={(event) => {
            const element = event.currentTarget;
            if (key) noteMediaSize(key, { width: element.videoWidth, height: element.videoHeight });
          }}
        />
        {segment?.kind === "image" && (
          <img
            src={imageUrl(segment.image)}
            alt=""
            style={croppedVideoStyle(size.width, size.height, rect)}
            onLoad={(event) =>
              noteMediaSize(key!, { width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })
            }
          />
        )}
      </div>
      {split && (
        <canvas
          ref={(element) => {
            slotCanvases[slot] = element;
          }}
          className="pane"
          style={{ height: pane.height }}
          width={Math.round(frame.width * devicePixelRatio)}
          height={Math.round(pane.height * devicePixelRatio)}
        />
      )}
    </div>
  );
}

/** Key of a segment's media in `mediaSizes`: a video id, or "image:<file>". */
export function mediaKey(segment: Segment, clipVideo: string): string {
  return segment.kind === "image" ? `image:${segment.image}` : (segment.media ?? clipVideo);
}
