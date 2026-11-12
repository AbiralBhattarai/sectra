import { useEffect, useLayoutEffect, useMemo, useRef, useState, type DragEvent, type PointerEvent, type WheelEvent } from "react";
import { addTransition, freezeAtPlayhead, insertionIndex } from "../editor/actions";
import { run } from "../editor/commands";
import { followsTracking } from "../editor/crop";
import { colorFilter } from "../editor/player/playback";
import { captionCues, clamp, isClipVideo, layout, MIN_SEGMENT, outputTime, type Placed } from "../editor/sequence";
import { selectedSegments, useEditor } from "../editor/store";
import type { Edl, Segment } from "../editor/types";
import { ContextMenu, type MenuItem } from "./ContextMenu";
import { dropIndex, maxTransition, trimCommand, trimmed, withSegment } from "./drafts";
import { snap, snapTargets } from "./snapping";
import { Waveform } from "./Waveform";

const MIN_VIEW_SECONDS = 1;
const TICK_STEPS = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
/** Media dragged in from the media bin. */
export const MEDIA_MIME = "application/x-sectra-media";
export type DraggedMedia = { kind: "video"; id: string; duration: number } | { kind: "image"; file: string };

type Drag =
  | { kind: "scrub" }
  | { kind: "trim"; id: string; edge: "start" | "end"; t: number }
  | { kind: "move"; id: string; t: number; x: number; moved: boolean }
  | { kind: "transition"; segmentId: string; cut: number; duration: number }
  | { kind: "item"; lane: "overlay" | "broll"; id: string; mode: "move" | "start" | "end"; grab: number; start: number; end: number };

/** Renders once the clip is loaded, so the track element exists before it's measured. */
export function Timeline() {
  const loaded = useEditor((s) => s.edl != null);
  return loaded ? <TimelineView /> : null;
}

function TimelineView() {
  const clipId = useEditor((s) => s.clip?.id);
  const video = useEditor((s) => s.video)!;
  const edl = useEditor((s) => s.edl)!;
  const peaks = useEditor((s) => s.peaks);
  const selection = useEditor((s) => s.selection);
  const snapping = useEditor((s) => s.snapping);
  const { seek, select, selectWord, setSnapping } = useEditor.getState();

  const trackRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [view, setView] = useState({ start: 0, end: 1 });
  const [drag, setDrag] = useState<Drag | null>(null);
  const [committing, setCommitting] = useState(false);
  const [menu, setMenu] = useState<{ x: number; y: number; items: (MenuItem | "-")[] } | null>(null);
  const [dropAt, setDropAt] = useState<{ lane: "video" | "broll"; t: number } | null>(null);

  useLayoutEffect(() => {
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(trackRef.current!);
    return () => observer.disconnect();
  }, []);

  const duration = useMemo(() => {
    const placed = layout(edl.segments);
    return placed.length ? placed[placed.length - 1].end : 0;
  }, [edl.segments]);
  // Frame the whole clip whenever a different clip opens.
  useEffect(() => setView(fit(duration)), [clipId]); // eslint-disable-line react-hooks/exhaustive-deps

  // While dragging, show the result without saving it.
  const shown = useMemo(() => draft(edl, drag, video.duration), [edl, drag, video.duration]);
  const placed = useMemo(() => layout(shown.segments), [shown.segments]);
  const cues = useMemo(() => captionCues(shown, shown.captions.style === "none" ? "clean" : shown.captions.style), [shown]);
  const total = placed.length ? placed[placed.length - 1].end : 0;

  const span = view.end - view.start;
  const pxPerSecond = width / span;
  const x = (t: number) => (t - view.start) * pxPerSecond;
  const timeAt = (clientX: number) => {
    const rect = trackRef.current!.getBoundingClientRect();
    return Math.max(0, view.start + (clientX - rect.left) / pxPerSecond);
  };
  const snapped = (t: number, ignore: string[] = []) =>
    snapping ? snap(t, snapTargets(edl, useEditor.getState().playhead, ignore), pxPerSecond) : t;
  const selectedIds = selectedSegments(selection);

  const begin = (event: PointerEvent, next: Drag) => {
    if (event.button !== 0 || committing) return;
    event.stopPropagation();
    trackRef.current!.setPointerCapture(event.pointerId);
    setDrag(next);
  };

  const onPointerMove = (event: PointerEvent) => {
    if (!drag || committing) return;
    const t = timeAt(event.clientX);
    switch (drag.kind) {
      case "scrub":
        return seek(Math.min(t, duration));
      case "trim":
        return setDrag({ ...drag, t: snapped(t, [drag.id]) });
      case "move":
        return setDrag({ ...drag, t, moved: drag.moved || Math.abs(event.clientX - drag.x) > 4 });
      case "transition": {
        const index = edl.segments.findIndex((s) => s.id === drag.segmentId);
        const d = clamp(Math.abs(t - drag.cut) * 2, 0.05, maxTransition(edl, index));
        return setDrag({ ...drag, duration: Math.round(d * 100) / 100 });
      }
      case "item": {
        const length = drag.end - drag.start;
        if (drag.mode === "move") {
          const start = snapped(Math.max(0, t - drag.grab), [drag.id]);
          return setDrag({ ...drag, start, end: start + length });
        }
        const edge = snapped(t, [drag.id]);
        return drag.mode === "start"
          ? setDrag({ ...drag, start: clamp(edge, 0, drag.end - MIN_SEGMENT) })
          : setDrag({ ...drag, end: Math.max(edge, drag.start + MIN_SEGMENT) });
      }
    }
  };

  const onPointerUp = () => {
    if (!drag || committing) return;
    const done = (pending?: Promise<unknown>) => {
      if (!pending) return setDrag(null);
      setCommitting(true);
      void pending.finally(() => {
        setDrag(null);
        setCommitting(false);
      });
    };
    switch (drag.kind) {
      case "trim": {
        const segment = shown.segments.find((s) => s.id === drag.id)!;
        return done(run(trimCommand(segment)));
      }
      case "move": {
        if (!drag.moved) return done();
        const to = dropIndex(edl, drag.id, drag.t);
        const from = edl.segments.findIndex((s) => s.id === drag.id);
        return done(to === from ? undefined : run({ op: "move", segment_id: drag.id, to_index: to }));
      }
      case "transition": {
        const segment = edl.segments.find((s) => s.id === drag.segmentId)!;
        return done(run({ op: "set_transition", segment_id: segment.id, type: segment.transition?.type ?? "fade", duration: drag.duration }));
      }
      case "item": {
        const start = round(drag.start);
        return done(
          drag.lane === "overlay"
            ? run({ op: "update_overlay", id: drag.id, start, end: round(drag.end) })
            : run({ op: "update_broll", id: drag.id, start, duration: round(drag.end - drag.start) }),
        );
      }
      default:
        return done();
    }
  };

  const onWheel = (event: WheelEvent) => {
    if (event.ctrlKey || event.metaKey) {
      const anchor = timeAt(event.clientX);
      const length = clamp(span * Math.exp(event.deltaY * 0.002), MIN_VIEW_SECONDS, Math.max(duration * 2, MIN_VIEW_SECONDS));
      const ratio = (anchor - view.start) / span;
      setView(within({ start: anchor - ratio * length, end: anchor - ratio * length + length }, duration));
    } else {
      const delta = ((event.deltaX || event.deltaY) / Math.max(width, 1)) * span;
      setView(within({ start: view.start + delta, end: view.end + delta }, duration));
    }
  };

  const selectSegment = (event: PointerEvent, id: string) => {
    if (event.shiftKey && selection?.kind === "segments") {
      const ids = selection.ids.includes(id) ? selection.ids.filter((s) => s !== id) : [...selection.ids, id];
      select(ids.length ? { kind: "segments", ids } : null);
    } else if (!selectedIds.includes(id)) {
      select({ kind: "segments", ids: [id] });
    }
  };

  const segmentMenu = (event: React.MouseEvent, p: Placed) => {
    event.preventDefault();
    const t = timeAt(event.clientX);
    const segment = p.segment;
    const ids = selectedIds.includes(segment.id) ? selectedIds : [segment.id];
    if (!selectedIds.includes(segment.id)) select({ kind: "segments", ids });
    const video = segment.kind === "video" ? segment : null;
    const speeds = [0.5, 1, 1.5, 2].map((speed) => ({
      label: `Speed ${speed}×${video?.speed === speed ? " ✓" : ""}`,
      action: () => run({ op: "update_segment", segment_ids: ids, speed }),
      disabled: !video,
    }));
    setMenu({
      x: event.clientX,
      y: event.clientY,
      items: [
        { label: "Split here", action: () => run({ op: "split", at: t }) },
        { label: "Duplicate", action: () => run(...ids.map((segment_id) => ({ op: "duplicate" as const, segment_id }))) },
        { label: "Freeze frame here (1 s)", action: () => (seek(t), freezeAtPlayhead()), disabled: segment.kind === "image" },
        { label: "Add transition in", action: () => addTransition(segment.id), disabled: p.index === 0 },
        "-",
        ...speeds,
        {
          label: video?.volume === 0 ? "Unmute" : "Mute",
          action: () => run({ op: "update_segment", segment_ids: ids, volume: video?.volume === 0 ? 1 : 0 }),
          disabled: !video,
        },
        { label: "Black & white", action: () => run({ op: "update_segment", segment_ids: ids, color_preset: "bw" }) },
        { label: "Reset colour", action: () => run({ op: "update_segment", segment_ids: ids, color_preset: "none" }) },
        "-",
        { label: "Delete (ripple)", action: () => run({ op: "delete", segment_ids: ids }) },
      ],
    });
  };

  const onDragOver = (event: DragEvent, lane: "video" | "broll") => {
    if (!event.dataTransfer.types.includes(MEDIA_MIME)) return;
    event.preventDefault();
    setDropAt({ lane, t: timeAt(event.clientX) });
  };
  const onDrop = (event: DragEvent, lane: "video" | "broll") => {
    setDropAt(null);
    const raw = event.dataTransfer.getData(MEDIA_MIME);
    if (!raw) return;
    event.preventDefault();
    const media = JSON.parse(raw) as DraggedMedia;
    const t = snapped(timeAt(event.clientX));
    if (lane === "video") {
      const at_index = insertionIndex(t);
      void (media.kind === "video"
        ? run({ op: "insert", media: media.id, start: 0, end: Math.min(media.duration, 10), at_index })
        : run({ op: "insert_image", image: media.file, duration: 3, at_index }));
    } else {
      void (media.kind === "video"
        ? run({ op: "add_broll", media: media.id, start: t, duration: Math.min(media.duration, 3) })
        : run({ op: "add_broll", image: media.file, start: t, duration: 3 }));
    }
  };

  const moving = drag?.kind === "move" && drag.moved ? drag : null;
  const dropX = moving ? dropMarkerX(edl, moving.id, moving.t, x) : null;

  return (
    <section className="panel timeline">
      <header className="panel-header">
        <h2>Timeline</h2>
        <span className="stage">
          ⌘/Ctrl + scroll to zoom · drag blocks to reorder, edges to trim · right-click for more
        </span>
        <label className="checkbox small" title="Snap to cuts, markers and the playhead (N)">
          <input type="checkbox" checked={snapping} onChange={(e) => setSnapping(e.target.checked)} />
          Snap
        </label>
        <button type="button" className="small" onClick={() => setView(fit(duration))}>
          Fit
        </button>
      </header>
      <div
        className={`track${committing ? " busy" : ""}`}
        ref={trackRef}
        onWheel={onWheel}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          seek(Math.min(timeAt(event.clientX), duration));
          select(null);
          begin(event, { kind: "scrub" });
        }}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onDragLeave={() => setDropAt(null)}
      >
        <Ruler view={view} width={width} />
        <div className="lane marker-lane" title="Markers (M to add, double-click to remove)">
          {shown.markers.map((m) => (
            <span
              key={m.id}
              className="marker"
              style={{ left: x(m.time) }}
              title={m.label || "Marker"}
              onPointerDown={(event) => {
                event.stopPropagation();
                seek(m.time);
              }}
              onDoubleClick={() => run({ op: "remove_marker", id: m.id })}
            />
          ))}
        </div>

        <div
          className={`lane video-lane${dropAt?.lane === "video" ? " drop" : ""}`}
          onDragOver={(e) => onDragOver(e, "video")}
          onDrop={(e) => onDrop(e, "video")}
        >
          {placed.map((p) => (
            <SegmentBlock
              key={p.segment.id}
              p={p}
              left={x(p.ownStart)}
              width={Math.max(2, x(p.ownEnd) - x(p.ownStart))}
              selected={selectedIds.includes(p.segment.id)}
              ghost={moving?.id === p.segment.id}
              clipVideo={video.id}
              peaks={peaks}
              text={blockText(shown, p)}
              onBody={(event) => {
                if (event.button !== 0) return;
                selectSegment(event, p.segment.id);
                begin(event, { kind: "move", id: p.segment.id, t: timeAt(event.clientX), x: event.clientX, moved: false });
              }}
              onEdge={(event, edge) => {
                select({ kind: "segments", ids: [p.segment.id] });
                begin(event, { kind: "trim", id: p.segment.id, edge, t: timeAt(event.clientX) });
              }}
              onMenu={(event) => segmentMenu(event, p)}
            />
          ))}
          {placed.slice(1).map((p) => {
            const transition = p.segment.transition;
            const cut = p.ownStart;
            if (!transition) {
              return (
                <button
                  key={`cut-${p.segment.id}`}
                  type="button"
                  className="cut-add"
                  style={{ left: x(cut) }}
                  title="Add a transition here (T)"
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={() => addTransition(p.segment.id)}
                >
                  +
                </button>
              );
            }
            const selected = selection?.kind === "transition" && selection.segmentId === p.segment.id;
            const half = (transition.duration / 2) * pxPerSecond;
            return (
              <div
                key={`tr-${p.segment.id}`}
                className={`transition-chip${selected ? " selected" : ""}`}
                style={{ left: x(cut) - Math.max(half, 6), width: Math.max(half * 2, 12) }}
                title={`${transition.type} · ${transition.duration.toFixed(2)} s (drag the edges)`}
                onPointerDown={(event) => {
                  event.stopPropagation();
                  select({ kind: "transition", segmentId: p.segment.id });
                }}
              >
                {(["start", "end"] as const).map((edge) => (
                  <span
                    key={edge}
                    className={`handle ${edge}`}
                    onPointerDown={(event) => {
                      select({ kind: "transition", segmentId: p.segment.id });
                      begin(event, { kind: "transition", segmentId: p.segment.id, cut, duration: transition.duration });
                    }}
                  />
                ))}
                <span className="chip-label">⧖</span>
              </div>
            );
          })}
          {dropX != null && <div className="drop-marker" style={{ left: dropX }} />}
          {dropAt?.lane === "video" && <div className="drop-marker" style={{ left: x(snapCut(placed, dropAt.t)) }} />}
        </div>

        <div
          className={`lane broll-lane${dropAt?.lane === "broll" ? " drop" : ""}`}
          title="B-roll (drop videos or images from the Media tab)"
          onDragOver={(e) => onDragOver(e, "broll")}
          onDrop={(e) => onDrop(e, "broll")}
        >
          {shown.broll.map((item) => (
            <ItemBlock
              key={item.id}
              left={x(item.start)}
              width={Math.max(4, item.duration * pxPerSecond)}
              selected={selection?.kind === "broll" && selection.id === item.id}
              label={item.image ?? "video"}
              onBody={(event) => {
                select({ kind: "broll", id: item.id });
                const t = timeAt(event.clientX);
                begin(event, { kind: "item", lane: "broll", id: item.id, mode: "move", grab: t - item.start, start: item.start, end: item.start + item.duration });
              }}
              onEdge={(event, mode) => {
                select({ kind: "broll", id: item.id });
                begin(event, { kind: "item", lane: "broll", id: item.id, mode, grab: 0, start: item.start, end: item.start + item.duration });
              }}
            />
          ))}
          {dropAt?.lane === "broll" && <div className="drop-marker" style={{ left: x(dropAt.t) }} />}
        </div>

        <div className="lane overlay-lane" title="Text overlays">
          {shown.overlays.map((overlay) => (
            <ItemBlock
              key={overlay.id}
              left={x(overlay.start)}
              width={Math.max(4, x(overlay.end) - x(overlay.start))}
              selected={selection?.kind === "overlay" && selection.id === overlay.id}
              label={overlay.text}
              onBody={(event) => {
                select({ kind: "overlay", id: overlay.id });
                const t = timeAt(event.clientX);
                begin(event, { kind: "item", lane: "overlay", id: overlay.id, mode: "move", grab: t - overlay.start, start: overlay.start, end: overlay.end });
              }}
              onEdge={(event, mode) => {
                select({ kind: "overlay", id: overlay.id });
                begin(event, { kind: "item", lane: "overlay", id: overlay.id, mode, grab: 0, start: overlay.start, end: overlay.end });
              }}
            />
          ))}
        </div>

        <div className="lane caption-lane">
          {cues
            .filter((c) => c.end > view.start && c.start < view.end)
            .map((cue) => (
              <span
                key={`${cue.start}-${cue.words[0].index}`}
                style={{ left: x(cue.start), width: Math.max(2, x(cue.end) - x(cue.start)) }}
                onPointerDown={(event) => {
                  event.stopPropagation();
                  seek(cue.start);
                  selectWord(cue.words[0].index);
                }}
              >
                {cue.words.map((w) => w.text).join(" ")}
              </span>
            ))}
        </div>

        {shown.music && (
          <div className="lane music-lane" title="Background music (loops under the clip)">
            <span style={{ left: x(0), width: Math.max(2, x(total) - x(0)) }}>♪ {shown.music.file}</span>
          </div>
        )}

        {shown.tracking?.enabled && (
          <div className="lane shots-lane" title="Face tracking shots (drag the preview to reframe one)">
            {shotBlocks(shown, placed).map((b) => (
              <span
                key={b.key}
                className={`face-${b.face % 4}`}
                style={{ left: x(b.start), width: Math.max(2, x(b.end) - x(b.start)) }}
                onPointerDown={(event) => {
                  event.stopPropagation();
                  seek(b.start);
                }}
              >
                Face {b.face + 1}
              </span>
            ))}
          </div>
        )}
        <PlayheadBar x={x} />
      </div>
      {menu && <ContextMenu {...menu} onClose={() => setMenu(null)} />}
    </section>
  );
}

function PlayheadBar({ x }: { x: (t: number) => number }) {
  const playhead = useEditor((s) => s.playhead);
  return <div className="playhead" style={{ left: x(playhead) }} />;
}

interface BlockProps {
  p: Placed;
  left: number;
  width: number;
  selected: boolean;
  ghost: boolean;
  clipVideo: string;
  peaks: ReturnType<typeof useEditor.getState>["peaks"];
  text: string;
  onBody: (event: PointerEvent) => void;
  onEdge: (event: PointerEvent, edge: "start" | "end") => void;
  onMenu: (event: React.MouseEvent) => void;
}

function SegmentBlock({ p, left, width, selected, ghost, clipVideo, peaks, text, onBody, onEdge, onMenu }: BlockProps) {
  const segment = p.segment;
  const badges = [
    segment.kind === "video" && segment.speed !== 1 && `${segment.speed}×`,
    segment.kind === "video" && segment.volume === 0 && "🔇",
    colorFilter(segment.color) && "◐",
    segment.crop && (("crop_to" in segment && segment.crop_to) ? "↗" : "⛶"),
    segment.kind !== "image" && segment.media && segment.media !== clipVideo && "▣",
  ].filter(Boolean);
  return (
    <div
      className={`segment segment-${segment.kind}${selected ? " selected" : ""}${ghost ? " ghost" : ""}`}
      style={{ left, width }}
      onPointerDown={onBody}
      onContextMenu={onMenu}
      title={text}
    >
      {segment.kind === "video" && segment.media === null && peaks && (
        <Waveform peaks={peaks} from={segment.start} to={segment.end} width={width} />
      )}
      <span className="segment-label">
        {badges.length > 0 && <b>{badges.join(" ")} </b>}
        {text}
      </span>
      {(["start", "end"] as const).map((edge) => (
        <span
          key={edge}
          className={`handle ${edge}`}
          onPointerDown={(event) => {
            if (event.button !== 0) return;
            onEdge(event, edge);
          }}
        />
      ))}
    </div>
  );
}

function ItemBlock(props: {
  left: number;
  width: number;
  selected: boolean;
  label: string;
  onBody: (event: PointerEvent) => void;
  onEdge: (event: PointerEvent, mode: "start" | "end") => void;
}) {
  return (
    <div
      className={`item${props.selected ? " selected" : ""}`}
      style={{ left: props.left, width: props.width }}
      onPointerDown={(event) => event.button === 0 && props.onBody(event)}
      title={props.label}
    >
      <span className="segment-label">{props.label}</span>
      {(["start", "end"] as const).map((edge) => (
        <span
          key={edge}
          className={`handle ${edge}`}
          onPointerDown={(event) => event.button === 0 && props.onEdge(event, edge)}
        />
      ))}
    </div>
  );
}

function Ruler({ view, width }: { view: { start: number; end: number }; width: number }) {
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

/** The EDL as the drag in progress would leave it. */
function draft(edl: Edl, drag: Drag | null, sourceLength: number | null): Edl {
  if (!drag) return edl;
  switch (drag.kind) {
    case "trim": {
      const p = layout(edl.segments).find((x) => x.segment.id === drag.id)!;
      const own = p.segment.kind === "video" && p.segment.media === null ? sourceLength : null;
      return withSegment(edl, trimmed(p.segment, drag.edge, drag.t, p.start, p.end, own));
    }
    case "transition":
      return {
        ...edl,
        segments: edl.segments.map((s) =>
          s.id === drag.segmentId && s.transition ? { ...s, transition: { ...s.transition, duration: drag.duration } } : s,
        ),
      };
    case "item":
      return drag.lane === "overlay"
        ? { ...edl, overlays: edl.overlays.map((o) => (o.id === drag.id ? { ...o, start: drag.start, end: drag.end } : o)) }
        : { ...edl, broll: edl.broll.map((b) => (b.id === drag.id ? { ...b, start: drag.start, duration: drag.end - drag.start } : b)) };
    default:
      return edl;
  }
}

/** Where the drop marker goes for a segment dragged to `t`. */
function dropMarkerX(edl: Edl, id: string, t: number, x: (t: number) => number): number {
  const others = layout(edl.segments.filter((s) => s.id !== id));
  const index = dropIndex(edl, id, t);
  if (!others.length) return x(0);
  return x(index < others.length ? others[index].ownStart : others[others.length - 1].ownEnd);
}

/** The cut nearest `t` (where an insert would go). */
function snapCut(placed: Placed[], t: number): number {
  const p = placed.find((q) => q.ownStart <= t && t < q.ownEnd);
  if (!p) return placed.length ? placed[placed.length - 1].ownEnd : 0;
  return t - p.ownStart < (p.ownEnd - p.ownStart) / 2 ? p.ownStart : p.ownEnd;
}

/** What a block shows: the words said in it, or what it is. */
function blockText(edl: Edl, p: Placed): string {
  const segment: Segment = p.segment;
  if (segment.kind === "image") return `🖼 ${segment.image}`;
  if (segment.kind === "freeze") return "❄ Freeze";
  if (segment.media !== null) return "Video";
  return edl.captions.words
    .filter((w) => w.start >= segment.start - 1e-6 && w.end <= segment.end + 1e-6)
    .map((w) => w.text)
    .join(" ");
}

/** Face-tracking shots on the output timeline, per segment that follows them. */
function shotBlocks(edl: Edl, placed: Placed[]) {
  const blocks: { key: string; face: number; start: number; end: number }[] = [];
  const shots = edl.tracking!.shots;
  for (const p of placed) {
    const segment = p.segment;
    if (segment.kind !== "video" || !isClipVideo(segment) || !followsTracking(edl, segment)) continue;
    shots.forEach((shot, i) => {
      const next = shots[i + 1]?.start ?? Infinity;
      const a = Math.max(shot.start, segment.start);
      const b = Math.min(next, segment.end);
      if (b > a) {
        blocks.push({
          key: `${segment.id}-${i}`,
          face: shot.face,
          start: Math.max(outputTime(p, a), p.ownStart),
          end: Math.min(outputTime(p, b), p.ownEnd),
        });
      }
    });
  }
  return blocks;
}

function fit(duration: number) {
  const padding = Math.max(0.5, duration * 0.04);
  return { start: 0, end: Math.max(duration + padding, MIN_VIEW_SECONDS) };
}

/** Shift (not shrink) a view so it starts at or after 0 and doesn't run far past the end. */
function within(view: { start: number; end: number }, duration: number) {
  const length = view.end - view.start;
  const start = clamp(view.start, 0, Math.max(0, duration + length * 0.5 - length));
  return { start, end: start + length };
}

const round = (t: number) => Math.round(t * 1000) / 1000;

function formatTick(t: number, step: number): string {
  const minutes = Math.floor(t / 60);
  const seconds = t % 60;
  const secondsText = step < 1 ? seconds.toFixed(step < 0.5 ? 2 : 1).padStart(step < 0.5 ? 5 : 4, "0") : String(Math.round(seconds)).padStart(2, "0");
  return `${minutes}:${secondsText}`;
}
