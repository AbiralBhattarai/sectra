import { useLayoutEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { CaptionOverlay } from "./CaptionOverlay";
import { run } from "./commands";
import { cropAt, panCrop, reframeCommands, splitApplies } from "./crop";
import { MusicPlayer } from "./MusicPlayer";
import { OverlayLayer } from "./OverlayLayer";
import { togglePlayback } from "./player/audio";
import { BrollLayer } from "./player/BrollLayer";
import { clipFade, slotTargets, transitionLook, transitionProgress } from "./player/playback";
import { mediaKey, SegmentLayer } from "./player/SegmentLayer";
import { usePlaybackEngine } from "./player/useEngine";
import { activeAt, layout, mediaTime, placedAt } from "./sequence";
import { useEditor } from "./store";
import { ASPECTS, type Crop } from "./types";

export function Preview() {
  const edl = useEditor((s) => s.edl)!;
  const video = useEditor((s) => s.video)!;
  const playhead = useEditor((s) => s.playhead);
  const playing = useEditor((s) => s.playing);
  const mediaSizes = useEditor((s) => s.mediaSizes);
  usePlaybackEngine();

  const areaRef = useRef<HTMLDivElement>(null);
  const [area, setArea] = useState({ width: 0, height: 0 });
  // Framing while dragging/zooming; committed as one edit on release, to whatever was
  // under the playhead when the gesture began.
  const [draft, setDraft] = useState<{ crop: Crop; at: number } | null>(null);
  const drag = useRef<{ x: number; y: number; crop: Crop } | null>(null);

  const placed = useMemo(() => layout(edl.segments), [edl.segments]);
  const duration = placed.length ? placed[placed.length - 1].end : 0;
  const owner = placedAt(placed, draft?.at ?? playhead);
  const ownerSize = owner ? mediaSizes[mediaKey(owner.segment, video.id)] : undefined;
  const currentCrop = owner ? cropAt(edl, owner.segment, mediaTime(owner, playhead)) : edl.crop;
  const crop = draft?.crop ?? currentCrop;

  const aspect = ASPECTS[edl.aspect];
  const frame =
    area.width / Math.max(area.height, 1) > aspect
      ? { width: area.height * aspect, height: area.height }
      : { width: area.width, height: area.width / aspect };

  useLayoutEffect(() => {
    const element = areaRef.current!;
    const observer = new ResizeObserver(([entry]) =>
      setArea({ width: entry.contentRect.width, height: entry.contentRect.height }),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const targets = slotTargets(placed, playhead);
  const active = activeAt(placed, playhead);
  // Fade through black/white: the wash belongs to the transition in progress.
  const incoming = active.find((p) => transitionProgress(edl.segments, p, playhead) != null);
  const wash =
    incoming?.segment.transition &&
    transitionLook(incoming.segment.transition.type, transitionProgress(edl.segments, incoming, playhead)!).wash;

  const onPointerDown = (event: PointerEvent) => {
    if (!owner) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { x: event.clientX, y: event.clientY, crop };
    setDraft({ crop, at: playhead });
  };
  const onPointerMove = (event: PointerEvent) => {
    if (!drag.current || !owner || !ownerSize) return;
    const split = splitApplies(edl, owner.segment);
    const { x, y, crop: start } = drag.current;
    const paneHeight = split ? frame.height / 2 : frame.height;
    const sourceWidth = split ? ownerSize.width / 2 : ownerSize.width;
    const moved = panCrop(start, event.clientX - x, event.clientY - y, frame.width, paneHeight, sourceWidth, ownerSize.height, split ? aspect * 2 : aspect);
    setDraft((d) => d && { ...d, crop: moved });
  };
  const commit = () => {
    drag.current = null;
    if (!draft || !owner) return setDraft(null);
    const commands = reframeCommands(edl, owner, draft.at, draft.crop);
    void run(...commands).finally(() => setDraft(null));
  };

  return (
    <div className="preview-column">
      <div className="preview-area" ref={areaRef}>
        <div
          className="frame"
          style={{ width: frame.width, height: frame.height }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={commit}
          title="Drag to reframe"
        >
          {targets.map((target, slot) => (
            <SegmentLayer
              key={slot}
              slot={slot}
              target={target}
              next={target ? (placed[target.placed.index + 1] ?? null) : null}
              frame={frame}
              draftCrop={draft && target?.placed === owner ? draft.crop : null}
            />
          ))}
          <BrollLayer frame={frame} />
          {wash && <div className="wash" style={{ background: wash.color, opacity: wash.opacity }} />}
          <div className="wash" style={{ background: "#000", opacity: 1 - clipFade(edl, playhead, duration) }} />
          <CaptionOverlay />
          <OverlayLayer />
        </div>
        <MusicPlayer />
      </div>
      <div className="transport">
        <button type="button" onClick={togglePlayback} aria-label={playing ? "Pause" : "Play"}>
          {playing ? "❚❚" : "▶"}
        </button>
        <Timecode duration={duration} />
        <label className="zoom">
          Zoom
          <input
            type="range"
            min={1}
            max={3}
            step={0.05}
            value={crop.scale}
            onChange={(event) => setDraft({ crop: { ...crop, scale: Number(event.target.value) }, at: draft?.at ?? playhead })}
            onPointerUp={commit}
            onKeyUp={commit}
          />
        </label>
      </div>
    </div>
  );
}

export function clock(seconds: number): string {
  const s = Math.max(0, seconds);
  const minutes = Math.floor(s / 60);
  return `${minutes}:${(s % 60).toFixed(1).padStart(4, "0")}`;
}

function Timecode({ duration }: { duration: number }) {
  const playhead = useEditor((s) => s.playhead);
  return (
    <span className="timecode">
      {clock(playhead)} / {clock(duration)}
    </span>
  );
}
