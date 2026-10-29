import { useEffect, useLayoutEffect, useMemo, useRef, useState, type PointerEvent, type WheelEvent } from "react";
import { paginate } from "../editor/captions";
import { clamp, outputToSource, trimRange } from "../editor/edlOps";
import { useEditor } from "../editor/store";
import type { Peaks, Span } from "../editor/types";

const MIN_VIEW_SECONDS = 2;
const TICK_STEPS = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];

interface Drag {
  index: number;
  edge: "start" | "end";
  time: number;
}

/** Renders once the clip is loaded, so the track element exists before it's measured. */
export function Timeline() {
  const loaded = useEditor((s) => s.edl != null);
  return loaded ? <TimelineView /> : null;
}

function TimelineView() {
  const clipId = useEditor((s) => s.clip?.id);
  const duration = useEditor((s) => s.video?.duration ?? 0);
  const edl = useEditor((s) => s.edl);
  const speech = useEditor((s) => s.speech);
  const peaks = useEditor((s) => s.peaks);
  const transcript = useEditor((s) => s.transcript);
  const playhead = useEditor((s) => s.playhead);
  const selectedRange = useEditor((s) => s.selectedRange);
  const selectedOverlay = useEditor((s) => s.selectedOverlay);
  const { edit, seek, selectRange, selectWord, selectOverlay } = useEditor.getState();

  const trackRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [view, setView] = useState<Span>({ start: 0, end: 1 });
  const [drag, setDrag] = useState<Drag | null>(null);

  useLayoutEffect(() => {
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(trackRef.current!);
    return () => observer.disconnect();
  }, []);

  // Frame the clip with some context whenever a different clip opens.
  useEffect(() => {
    if (edl) setView(fitView(edl.ranges, duration));
  }, [clipId]); // eslint-disable-line react-hooks/exhaustive-deps

  // While dragging a handle, show the trimmed result without recording undo steps.
  const shown = useMemo(
    () => (edl && drag ? trimRange(edl, drag.index, drag.edge, drag.time, duration, transcript) : edl),
    [edl, drag, duration, transcript],
  );
  const pages = useMemo(
    () => (shown ? paginate(shown.captions.words, shown.captions.style === "none" ? "clean" : shown.captions.style) : []),
    [shown],
  );
  if (!shown) return null;

  const span = view.end - view.start;
  const x = (t: number) => ((t - view.start) / span) * width;
  const timeAt = (clientX: number) => {
    const rect = trackRef.current!.getBoundingClientRect();
    return clamp(view.start + ((clientX - rect.left) / rect.width) * span, 0, duration);
  };

  const onTrackPointerDown = (event: PointerEvent) => {
    const t = timeAt(event.clientX);
    seek(t);
    const index = shown.ranges.findIndex((r) => t >= r.start && t <= r.end);
    selectRange(index === -1 ? null : index);
  };

  const onHandleDown = (event: PointerEvent, index: number, edge: "start" | "end") => {
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    selectRange(index);
    setDrag({ index, edge, time: shown.ranges[index][edge] });
  };
  const onHandleMove = (event: PointerEvent) => {
    if (!drag) return;
    const time = timeAt(event.clientX);
    setDrag({ ...drag, time });
    seek(clamp(time, 0, duration));
  };
  const onHandleUp = () => {
    if (drag) edit((e) => trimRange(e, drag.index, drag.edge, drag.time, duration, transcript));
    setDrag(null);
  };

  const onWheel = (event: WheelEvent) => {
    if (event.ctrlKey || event.metaKey) {
      const anchor = timeAt(event.clientX);
      const factor = Math.exp(event.deltaY * 0.002);
      const length = clamp(span * factor, MIN_VIEW_SECONDS, Math.max(duration, MIN_VIEW_SECONDS));
      const ratio = (anchor - view.start) / span;
      setView(within({ start: anchor - ratio * length, end: anchor - ratio * length + length }, duration));
    } else {
      const delta = ((event.deltaX || event.deltaY) / Math.max(width, 1)) * span;
      setView(within({ start: view.start + delta, end: view.end + delta }, duration));
    }
  };

  return (
    <section className="panel timeline">
      <header className="panel-header">
        <h2>Timeline</h2>
        <span className="stage">⌘/Ctrl + scroll to zoom · scroll to pan · drag range edges to trim</span>
        <button type="button" className="small" onClick={() => setView(fitView(shown.ranges, duration))}>
          Fit
        </button>
      </header>
      <div className="track" ref={trackRef} onWheel={onWheel} onPointerDown={onTrackPointerDown}>
        <Ruler view={view} width={width} />
        <div className="lane wave-lane">
          <Waveform peaks={peaks} view={view} width={width} />
          {shown.ranges.map((range, index) => (
            <div
              key={index}
              className={`range${index === selectedRange ? " selected" : ""}`}
              style={{ left: x(range.start), width: Math.max(1, x(range.end) - x(range.start)) }}
            >
              {(["start", "end"] as const).map((edge) => (
                <span
                  key={edge}
                  className={`handle ${edge}`}
                  onPointerDown={(event) => onHandleDown(event, index, edge)}
                  onPointerMove={onHandleMove}
                  onPointerUp={onHandleUp}
                />
              ))}
            </div>
          ))}
        </div>
        <div className="lane speech-lane" title="Speech detected by VAD">
          {speech
            .filter((s) => s.end > view.start && s.start < view.end)
            .map((s, i) => (
              <span key={i} style={{ left: x(s.start), width: Math.max(1, x(s.end) - x(s.start)) }} />
            ))}
        </div>
        <div className="lane caption-lane">
          {pages
            .filter((p) => p.end > view.start && p.start < view.end)
            .map((page) => (
              <span
                key={`${page.start}-${page.words[0].text}`}
                style={{ left: x(page.start), width: Math.max(2, x(page.end) - x(page.start)) }}
                onPointerDown={(event) => {
                  event.stopPropagation();
                  seek(page.start);
                  selectWord(shown.captions.words.indexOf(page.words[0]));
                }}
              >
                {page.words.map((w) => w.text).join(" ")}
              </span>
            ))}
        </div>
        <div className="lane overlay-lane" title="Text overlays">
          {shown.overlays.map((overlay, index) => {
            // Overlays live on the output timeline; place them where that time plays.
            const start = outputToSource(overlay.start, shown.ranges);
            const end = outputToSource(overlay.end, shown.ranges);
            return (
              <span
                key={index}
                className={index === selectedOverlay ? "selected" : undefined}
                style={{ left: x(start), width: Math.max(2, x(end) - x(start)) }}
                onPointerDown={(event) => {
                  event.stopPropagation();
                  seek(start);
                  selectOverlay(index);
                }}
              >
                {overlay.text}
              </span>
            );
          })}
        </div>
        <div className="playhead" style={{ left: x(playhead) }} />
      </div>
    </section>
  );
}

function Ruler({ view, width }: { view: Span; width: number }) {
  const span = view.end - view.start;
  // Aim for a label roughly every 80 px.
  const step = TICK_STEPS.find((s) => (s / span) * width >= 80) ?? TICK_STEPS[TICK_STEPS.length - 1];
  const ticks: number[] = [];
  for (let t = Math.ceil(view.start / step) * step; t <= view.end; t += step) ticks.push(t);
  return (
    <div className="lane ruler">
      {ticks.map((t) => (
        <span key={t} style={{ left: ((t - view.start) / span) * width }}>
          {formatTick(t, step)}
        </span>
      ))}
    </div>
  );
}

function Waveform({ peaks, view, width }: { peaks: Peaks | null; view: Span; width: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const maxPeak = useMemo(() => (peaks ? Math.max(0.01, ...peaks.peaks) : 1), [peaks]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !peaks || width === 0) return;
    const ratio = window.devicePixelRatio || 1;
    const height = canvas.clientHeight;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    const context = canvas.getContext("2d")!;
    context.scale(ratio, ratio);
    context.clearRect(0, 0, width, height);
    context.fillStyle = getComputedStyle(canvas).color;
    const perPixel = (view.end - view.start) / width;
    for (let px = 0; px < width; px++) {
      const from = Math.floor((view.start + px * perPixel) * peaks.per_second);
      const to = Math.max(from + 1, Math.ceil((view.start + (px + 1) * perPixel) * peaks.per_second));
      let peak = 0;
      for (let i = Math.max(0, from); i < Math.min(to, peaks.peaks.length); i++) peak = Math.max(peak, peaks.peaks[i]);
      const bar = Math.max(1, (peak / maxPeak) * (height - 4));
      context.fillRect(px, (height - bar) / 2, 1, bar);
    }
  }, [peaks, view, width, maxPeak]);

  return <canvas ref={canvasRef} className="waveform" />;
}

function fitView(ranges: Span[], duration: number): Span {
  const start = ranges[0].start;
  const end = ranges[ranges.length - 1].end;
  const padding = Math.max(5, (end - start) * 0.25);
  return within({ start: start - padding, end: end + padding }, duration);
}

/** Shift (not shrink) a view so it stays inside [0, duration]. */
function within(view: Span, duration: number): Span {
  const length = Math.min(view.end - view.start, Math.max(duration, MIN_VIEW_SECONDS));
  const start = clamp(view.start, 0, Math.max(0, duration - length));
  return { start, end: start + length };
}

function formatTick(t: number, step: number): string {
  const minutes = Math.floor(t / 60);
  const seconds = t % 60;
  const secondsText = step < 1 ? seconds.toFixed(1).padStart(4, "0") : String(Math.round(seconds)).padStart(2, "0");
  return `${minutes}:${secondsText}`;
}
