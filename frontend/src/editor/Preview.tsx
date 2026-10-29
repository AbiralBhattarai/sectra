import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent } from "react";
import { mediaUrl } from "../api/client";
import { CaptionOverlay } from "./CaptionOverlay";
import { croppedVideoStyle, panCrop } from "./crop";
import { MusicPlayer } from "./MusicPlayer";
import { OverlayLayer } from "./OverlayLayer";
import { nextPlayable, outputDuration, sourceToOutput } from "./edlOps";
import { useEditor } from "./store";
import { ASPECTS, type Crop } from "./types";

export function Preview() {
  const video = useEditor((s) => s.video)!;
  const edl = useEditor((s) => s.edl)!;
  const playhead = useEditor((s) => s.playhead);
  const playing = useEditor((s) => s.playing);
  const { edit, setMedia, setPlayhead, togglePlay, seek } = useEditor.getState();

  const areaRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [area, setArea] = useState({ width: 0, height: 0 });
  // Crop while dragging/zooming; committed as one undo step on release.
  const [draftCrop, setDraftCrop] = useState<Crop | null>(null);
  const drag = useRef<{ x: number; y: number; crop: Crop } | null>(null);

  const aspect = ASPECTS[edl.aspect];
  const crop = draftCrop ?? edl.crop;
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

  // Playback loop: follow the video, hop over cuts, stop after the last range.
  useEffect(() => {
    const media = videoRef.current!;
    setMedia(media);
    let handle = 0;
    const tick = () => {
      const { edl: current } = useEditor.getState();
      if (current && !media.paused) {
        const next = nextPlayable(media.currentTime, current.ranges);
        if (next === null) {
          media.pause();
          media.currentTime = current.ranges[current.ranges.length - 1].end;
        } else if (next - media.currentTime > 0.02) {
          media.currentTime = next;
        }
      }
      setPlayhead(media.currentTime, !media.paused);
      handle = requestAnimationFrame(tick);
    };
    handle = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(handle);
      setMedia(null);
    };
  }, [setMedia, setPlayhead]);

  const onPointerDown = (event: PointerEvent) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { x: event.clientX, y: event.clientY, crop };
  };
  const onPointerMove = (event: PointerEvent) => {
    if (!drag.current || !video.width || !video.height) return;
    const { x, y, crop: start } = drag.current;
    setDraftCrop(
      panCrop(start, event.clientX - x, event.clientY - y, frame.width, frame.height, video.width, video.height, aspect),
    );
  };
  const commitCrop = () => {
    drag.current = null;
    if (draftCrop) edit((e) => ({ ...e, crop: draftCrop }));
    setDraftCrop(null);
  };

  const total = outputDuration(edl.ranges);
  return (
    <div className="preview-column">
      <div className="preview-area" ref={areaRef}>
        <div
          className="frame"
          style={{ width: frame.width, height: frame.height }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={commitCrop}
          title="Drag to reframe"
        >
          <video
            ref={videoRef}
            src={mediaUrl(video.id, "source.mp4")}
            style={croppedVideoStyle(video.width ?? 16, video.height ?? 9, aspect, crop)}
            preload="auto"
            onLoadedMetadata={() => seek(edl.ranges[0].start)}
            onClick={togglePlay}
          />
          <CaptionOverlay />
          <OverlayLayer />
        </div>
        <MusicPlayer />
      </div>
      <div className="transport">
        <button type="button" onClick={togglePlay} aria-label={playing ? "Pause" : "Play"}>
          {playing ? "❚❚" : "▶"}
        </button>
        <span className="timecode">
          {clock(sourceToOutput(playhead, edl.ranges))} / {clock(total)}
        </span>
        <label className="zoom">
          Zoom
          <input
            type="range"
            min={1}
            max={3}
            step={0.05}
            value={crop.scale}
            onChange={(event) => setDraftCrop({ ...crop, scale: Number(event.target.value) })}
            onPointerUp={commitCrop}
            onKeyUp={commitCrop}
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
