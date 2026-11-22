import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent } from "react";
import { mediaUrl } from "../api/client";
import { CaptionOverlay } from "./CaptionOverlay";
import { CharacterLayer } from "./CharacterLayer";
import {
  cropAt,
  croppedVideoStyle,
  cropWindow,
  facecamWindow,
  panCrop,
  pipBox,
  OUTPUT_SIZES,
  setCropAt,
  streamerMode,
  trackingOn,
  zoomAt,
} from "./crop";
import { MusicPlayer } from "./MusicPlayer";
import { OverlayLayer } from "./OverlayLayer";
import { nextPlayable, outputDuration, sourceToOutput } from "./edlOps";
import { useEditor } from "./store";
import { ASPECTS, type Crop, type Facecam } from "./types";

export function Preview() {
  const video = useEditor((s) => s.video)!;
  const edl = useEditor((s) => s.edl)!;
  const playhead = useEditor((s) => s.playhead);
  const playing = useEditor((s) => s.playing);
  const { edit, setMedia, setPlayhead, togglePlay, seek } = useEditor.getState();

  const areaRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [area, setArea] = useState({ width: 0, height: 0 });
  // Crop while dragging/zooming; committed as one undo step on release, to the shot
  // that was under the playhead when the gesture began (face tracking).
  const [draftCrop, setDraftCrop] = useState<Crop | null>(null);
  const draftTime = useRef(0);
  const drag = useRef<{ x: number; y: number; crop: Crop } | null>(null);
  // Streamer mode: the facecam box's own drag/zoom draft, committed the same way.
  const pipCanvasRef = useRef<HTMLCanvasElement>(null);
  const [draftCam, setDraftCam] = useState<Facecam | null>(null);
  const camDrag = useRef<{ x: number; y: number; cam: Facecam } | null>(null);

  const aspect = ASPECTS[edl.aspect];
  const crop = draftCrop ?? cropAt(edl, playhead);
  const frame =
    area.width / Math.max(area.height, 1) > aspect
      ? { width: area.height * aspect, height: area.height }
      : { width: area.width, height: area.width / aspect };
  const sourceWidth = video.width ?? 16;
  const sourceHeight = video.height ?? 9;
  // Split screen: each half of the source fills half of the frame, left half on top.
  // As the render: streamer mode, then tracking, win over the split.
  const streamer = streamerMode(edl);
  const split = edl.split_screen && !trackingOn(edl) && !streamer;
  const pane = split
    ? { width: frame.width, height: frame.height / 2, sourceWidth: sourceWidth / 2, aspect: aspect * 2 }
    : { width: frame.width, height: frame.height, sourceWidth, aspect };
  const rect = cropWindow(pane.sourceWidth, sourceHeight, pane.aspect, crop);
  // Zoom-ins scale the framed picture about the pane's centre, as the render does.
  const zoom = zoomAt(edl, playhead);
  // Read by the canvas loop, which draws the right half into the bottom pane.
  const rightRect = useRef(rect);
  rightRect.current = { ...rect, x: rect.x + pane.sourceWidth };
  // Streamer mode: the facecam box (frame pixels) and the source window drawn into it.
  const cam = draftCam ?? edl.facecam ?? null;
  const [outWidth] = OUTPUT_SIZES[edl.aspect];
  const box = pipBox(edl.aspect);
  const toFrame = frame.width / outWidth;
  const pip = { x: box.x * toFrame, y: box.y * toFrame, width: box.width * toFrame, height: box.height * toFrame };
  const camRect = useRef(rect);
  if (cam) camRect.current = facecamWindow(sourceWidth, sourceHeight, edl.aspect, cam);

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

  // The bottom pane is a canvas copying frames from the one <video>, so both halves stay in sync.
  useEffect(() => {
    if (!split) return;
    const media = videoRef.current!;
    let handle = 0;
    const draw = () => {
      const canvas = canvasRef.current;
      if (canvas && media.readyState >= media.HAVE_CURRENT_DATA) {
        const { x, y, width, height } = rightRect.current;
        canvas.getContext("2d")!.drawImage(media, x, y, width, height, 0, 0, canvas.width, canvas.height);
      }
      handle = requestAnimationFrame(draw);
    };
    handle = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(handle);
  }, [split]);

  // Streamer mode: the facecam box is a canvas fed from the same <video>, like the split.
  useEffect(() => {
    if (!streamer) return;
    const media = videoRef.current!;
    let handle = 0;
    const draw = () => {
      const canvas = pipCanvasRef.current;
      if (canvas && media.readyState >= media.HAVE_CURRENT_DATA) {
        const { x, y, width, height } = camRect.current;
        canvas.getContext("2d")!.drawImage(media, x, y, width, height, 0, 0, canvas.width, canvas.height);
      }
      handle = requestAnimationFrame(draw);
    };
    handle = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(handle);
  }, [streamer]);

  // Dragging inside the box pans the facecam's source window (not the gameplay crop).
  const onCamDown = (event: PointerEvent) => {
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    camDrag.current = { x: event.clientX, y: event.clientY, cam: cam! };
  };
  const onCamMove = (event: PointerEvent) => {
    event.stopPropagation();
    if (!camDrag.current || !video.width || !video.height) return;
    const { x, y, cam: start } = camDrag.current;
    const moved = panCrop(
      start,
      event.clientX - x,
      event.clientY - y,
      pip.width,
      pip.height,
      sourceWidth,
      sourceHeight,
      box.width / box.height,
    );
    setDraftCam({ ...start, x: moved.x, y: moved.y });
  };
  const commitCam = (event?: { stopPropagation: () => void }) => {
    event?.stopPropagation();
    camDrag.current = null;
    if (draftCam) edit((e) => ({ ...e, facecam: draftCam }));
    setDraftCam(null);
  };

  const onPointerDown = (event: PointerEvent) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { x: event.clientX, y: event.clientY, crop };
    draftTime.current = playhead;
  };
  const onPointerMove = (event: PointerEvent) => {
    if (!drag.current || !video.width || !video.height) return;
    const { x, y, crop: start } = drag.current;
    setDraftCrop(
      panCrop(start, event.clientX - x, event.clientY - y, pane.width, pane.height, pane.sourceWidth, sourceHeight, pane.aspect),
    );
  };
  const commitCrop = () => {
    drag.current = null;
    if (draftCrop) edit((e) => setCropAt(e, draftTime.current, draftCrop));
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
          <div className="pane" style={{ height: pane.height }}>
            <div className="zoomer" style={zoom === 1 ? undefined : { transform: `scale(${zoom})` }}>
              <video
                ref={videoRef}
                src={mediaUrl(video.id, "source.mp4")}
                style={croppedVideoStyle(sourceWidth, sourceHeight, rect)}
                preload="auto"
                onLoadedMetadata={() => seek(edl.ranges[0].start)}
                onClick={togglePlay}
              />
            </div>
          </div>
          {split && (
            <canvas
              ref={canvasRef}
              className="pane"
              style={{ height: pane.height }}
              width={Math.round(pane.width * devicePixelRatio)}
              height={Math.round(pane.height * devicePixelRatio)}
            />
          )}
          {streamer && (
            <canvas
              ref={pipCanvasRef}
              className="pip"
              style={{ left: pip.x, top: pip.y, width: pip.width, height: pip.height }}
              width={Math.round(pip.width * devicePixelRatio)}
              height={Math.round(pip.height * devicePixelRatio)}
              title="Drag to put the streamer's face in the box"
              onPointerDown={onCamDown}
              onPointerMove={onCamMove}
              onPointerUp={commitCam}
            />
          )}
          <CharacterLayer />
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
            onChange={(event) => {
              if (!draftCrop) draftTime.current = playhead;
              setDraftCrop({ ...crop, scale: Number(event.target.value) });
            }}
            onPointerUp={commitCrop}
            onKeyUp={commitCrop}
          />
        </label>
        {cam && (
          <label className="zoom" title="Zoom of the facecam box">
            Cam zoom
            <input
              type="range"
              min={1}
              max={8}
              step={0.1}
              value={cam.scale}
              onChange={(event) => setDraftCam({ ...cam, scale: Number(event.target.value) })}
              onPointerUp={() => commitCam()}
              onKeyUp={() => commitCam()}
            />
          </label>
        )}
      </div>
    </div>
  );
}

export function clock(seconds: number): string {
  const s = Math.max(0, seconds);
  const minutes = Math.floor(s / 60);
  return `${minutes}:${(s % 60).toFixed(1).padStart(4, "0")}`;
}
