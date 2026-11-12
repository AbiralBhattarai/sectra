import { useMemo } from "react";
import { maxTransition } from "../timeline/drafts";
import { freezeAtPlayhead } from "./actions";
import { run } from "./commands";
import { NumberField, Slider } from "./controls";
import { cropAt } from "./crop";
import { OverlayForm } from "./OverlayEditor";
import { clock } from "./Preview";
import { layout, mediaTime, placedAt, segmentLength } from "./sequence";
import { useEditor } from "./store";
import type { BrollItem, Color, ColorPreset, Edl, Segment, TransitionType } from "./types";
import { SHORTCUTS } from "./useShortcuts";

const PRESETS: { value: ColorPreset; label: string }[] = [
  { value: "none", label: "None" },
  { value: "bw", label: "B&W" },
  { value: "warm", label: "Warm" },
  { value: "cool", label: "Cool" },
  { value: "vivid", label: "Vivid" },
  { value: "vintage", label: "Vintage" },
  { value: "dramatic", label: "Dramatic" },
];
const TRANSITIONS: { value: TransitionType; label: string }[] = [
  { value: "fade", label: "Crossfade" },
  { value: "dissolve", label: "Dissolve" },
  { value: "fadeblack", label: "Dip to black" },
  { value: "fadewhite", label: "Dip to white" },
  { value: "wipeleft", label: "Wipe ←" },
  { value: "wiperight", label: "Wipe →" },
  { value: "wipeup", label: "Wipe ↑" },
  { value: "wipedown", label: "Wipe ↓" },
  { value: "slideleft", label: "Slide ←" },
  { value: "slideright", label: "Slide →" },
  { value: "slideup", label: "Slide ↑" },
  { value: "slidedown", label: "Slide ↓" },
  { value: "circleopen", label: "Circle" },
  { value: "zoomin", label: "Zoom" },
  { value: "pixelize", label: "Pixelize" },
];
const SPEEDS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4];

/** Properties of whatever is selected on the timeline (the clip when nothing is). */
export function Inspector() {
  const edl = useEditor((s) => s.edl)!;
  const selection = useEditor((s) => s.selection);
  if (selection?.kind === "segments") {
    const segments = edl.segments.filter((s) => selection.ids.includes(s.id));
    if (segments.length) return <SegmentInspector edl={edl} segments={segments} />;
  }
  if (selection?.kind === "transition") {
    const index = edl.segments.findIndex((s) => s.id === selection.segmentId);
    if (index > 0 && edl.segments[index].transition) return <TransitionInspector edl={edl} index={index} />;
  }
  if (selection?.kind === "broll") {
    const item = edl.broll.find((b) => b.id === selection.id);
    if (item) return <BrollInspector item={item} />;
  }
  if (selection?.kind === "overlay") {
    const overlay = edl.overlays.find((o) => o.id === selection.id);
    if (overlay) return (
      <div className="tab-body">
        <h3>Text</h3>
        <OverlayForm overlay={overlay} />
      </div>
    );
  }
  return <ClipInspector edl={edl} />;
}

function SegmentInspector({ edl, segments }: { edl: Edl; segments: Segment[] }) {
  const playhead = useEditor((s) => s.playhead);
  const first = segments[0];
  const ids = segments.map((s) => s.id);
  const videos = segments.every((s) => s.kind === "video") ? (segments as Extract<Segment, { kind: "video" }>[]) : null;
  const video = videos?.[0];
  const update = (fields: Omit<Extract<Parameters<typeof run>[0], { op: "update_segment" }>, "op" | "segment_ids">) =>
    run({ op: "update_segment", segment_ids: ids, ...fields });
  const placed = useMemo(() => layout(edl.segments), [edl.segments]);
  const here = placedAt(placed, playhead);
  const p = placed.find((q) => q.segment.id === first.id)!;
  const effective = cropAt(edl, first, here?.segment.id === first.id ? mediaTime(here, playhead) : mediaTime(p, p.start));
  const kenBurns = first.kind !== "freeze" && first.crop_to != null;

  return (
    <div className="tab-body inspector">
      <h3>
        {segments.length > 1 ? `${segments.length} segments` : describe(first)}
        <span className="stage"> · {clock(segments.reduce((sum, s) => sum + segmentLength(s), 0))}</span>
      </h3>

      {video && videos && (
        <section>
          <label className="field">
            Speed
            <select value={video.speed} onChange={(e) => update({ speed: Number(e.target.value) })}>
              {[...new Set([...SPEEDS, video.speed])].sort((a, b) => a - b).map((s) => (
                <option key={s} value={s}>
                  {s}×
                </option>
              ))}
            </select>
          </label>
          <Slider
            label="Volume"
            value={video.volume}
            min={0}
            max={2}
            step={0.05}
            format={(v) => (v === 0 ? "muted" : `${Math.round(v * 100)}%`)}
            onCommit={(volume) => update({ volume })}
          />
          <div className="row">
            <button type="button" className="small" onClick={() => update({ volume: video.volume === 0 ? 1 : 0 })}>
              {video.volume === 0 ? "Unmute" : "Mute"}
            </button>
            <NumberField label="Fade in" value={video.audio_fade_in} min={0} step={0.1} onCommit={(v) => update({ audio_fade_in: v })} />
            <NumberField label="Fade out" value={video.audio_fade_out} min={0} step={0.1} onCommit={(v) => update({ audio_fade_out: v })} />
          </div>
          {segments.length === 1 && (
            <div className="row">
              <NumberField label="In (source s)" value={video.start} min={0} onCommit={(v) => run({ op: "trim", segment_id: video.id, start: v })} />
              <NumberField label="Out (source s)" value={video.end} min={0} onCommit={(v) => run({ op: "trim", segment_id: video.id, end: v })} />
            </div>
          )}
        </section>
      )}
      {first.kind !== "video" && segments.length === 1 && (
        <NumberField label="Length (s)" value={first.duration} min={0.1} max={60} onCommit={(v) => run({ op: "trim", segment_id: first.id, duration: v })} />
      )}

      <section>
        <h4>Colour</h4>
        <div className="chips">
          {PRESETS.map((preset) => (
            <button key={preset.value} type="button" className="small" onClick={() => update({ color_preset: preset.value })}>
              {preset.label}
            </button>
          ))}
        </div>
        <ColorSliders color={first.color} onCommit={(color) => update({ color })} />
      </section>

      <section>
        <h4>Framing</h4>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={first.crop != null}
            onChange={(e) => update(e.target.checked ? { crop: effective } : { clear_crop: true })}
          />
          Own framing (ignores face tracking and the clip's crop)
        </label>
        {first.crop && first.kind !== "freeze" && (
          <>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={kenBurns}
                onChange={(e) =>
                  e.target.checked
                    ? update({ crop_to: { ...first.crop!, scale: Math.min(5, first.crop!.scale * 1.3) } })
                    : run(
                        { op: "update_segment", segment_ids: ids, clear_crop: true },
                        { op: "update_segment", segment_ids: ids, crop: first.crop! },
                      )
                }
              />
              Ken Burns (slow zoom / pan)
            </label>
            {kenBurns && first.crop_to && (
              <>
                <Slider label="Start zoom" value={first.crop.scale} min={1} max={5} step={0.05} format={(v) => `${v.toFixed(2)}×`} onCommit={(scale) => update({ crop: { ...first.crop!, scale } })} />
                <Slider label="End zoom" value={first.crop_to.scale} min={1} max={5} step={0.05} format={(v) => `${v.toFixed(2)}×`} onCommit={(scale) => update({ crop_to: { ...first.crop_to!, scale } })} />
                <p className="stage">Drag the preview in the first half of the segment to place the start, in the second half for the end.</p>
              </>
            )}
          </>
        )}
      </section>

      <section className="row">
        <button type="button" className="small" onClick={() => freezeAtPlayhead()} disabled={here?.segment.id !== first.id || first.kind === "image"}>
          Freeze frame at playhead
        </button>
        <button type="button" className="small" onClick={() => run(...ids.map((segment_id) => ({ op: "duplicate" as const, segment_id })))}>
          Duplicate
        </button>
        <button type="button" className="small danger" onClick={() => run({ op: "delete", segment_ids: ids })}>
          Delete
        </button>
      </section>
    </div>
  );
}

function ColorSliders({ color, onCommit }: { color: Color; onCommit: (color: Color) => unknown }) {
  const fields: [keyof Color, string, number, number, number][] = [
    ["brightness", "Brightness", 0, 2, 0.01],
    ["contrast", "Contrast", 0, 2, 0.01],
    ["saturation", "Saturation", 0, 3, 0.01],
    ["sepia", "Sepia", 0, 1, 0.01],
    ["hue", "Hue", -180, 180, 1],
  ];
  return (
    <>
      {fields.map(([key, label, min, max, step]) => (
        <Slider key={key} label={label} value={color[key]} min={min} max={max} step={step} onCommit={(v) => onCommit({ ...color, [key]: v })} />
      ))}
    </>
  );
}

function TransitionInspector({ edl, index }: { edl: Edl; index: number }) {
  const segment = edl.segments[index];
  const transition = segment.transition!;
  const max = maxTransition(edl, index);
  const set = (fields: { type?: TransitionType; duration?: number }) =>
    run({ op: "set_transition", segment_id: segment.id, type: transition.type, duration: transition.duration, ...fields });
  return (
    <div className="tab-body inspector">
      <h3>Transition into segment {index + 1}</h3>
      <div className="chips grid">
        {TRANSITIONS.map((t) => (
          <button key={t.value} type="button" className={`small${t.value === transition.type ? " active" : ""}`} onClick={() => set({ type: t.value })}>
            {t.label}
          </button>
        ))}
      </div>
      <Slider label="Duration" value={transition.duration} min={0.05} max={Math.max(0.05, Math.floor(max * 100) / 100)} step={0.05} format={(v) => `${v.toFixed(2)} s`} onCommit={(duration) => set({ duration })} />
      <button type="button" className="small danger" onClick={() => run({ op: "remove_transition", segment_id: segment.id })}>
        Remove (hard cut)
      </button>
    </div>
  );
}

function BrollInspector({ item }: { item: BrollItem }) {
  const update = (fields: Partial<BrollItem>) => run({ op: "update_broll", id: item.id, ...fields });
  return (
    <div className="tab-body inspector">
      <h3>B-roll · {item.image ?? "video"}</h3>
      <label className="field">
        Layout
        <select value={item.layout} onChange={(e) => update({ layout: e.target.value as BrollItem["layout"] })}>
          <option value="full">Full frame</option>
          <option value="pip">Picture in picture</option>
        </select>
      </label>
      {item.layout === "pip" && (
        <>
          <Slider label="Size" value={item.size} min={0.1} max={1} step={0.01} format={(v) => `${Math.round(v * 100)}%`} onCommit={(size) => update({ size })} />
          <Slider label="Horizontal" value={item.x} min={0} max={1} step={0.01} onCommit={(x) => update({ x })} />
          <Slider label="Vertical" value={item.y} min={0} max={1} step={0.01} onCommit={(y) => update({ y })} />
        </>
      )}
      <div className="row">
        <NumberField label="Start (s)" value={item.start} min={0} onCommit={(start) => update({ start })} />
        <NumberField label="Length (s)" value={item.duration} min={0.1} onCommit={(duration) => update({ duration })} />
        {item.media && <NumberField label="From (s)" value={item.media_start} min={0} onCommit={(media_start) => update({ media_start })} />}
      </div>
      <Slider label="Fade" value={item.fade} min={0} max={Math.max(0, item.duration / 2)} step={0.05} format={(v) => `${v.toFixed(2)} s`} onCommit={(fade) => update({ fade })} />
      {item.media && <Slider label="Its sound" value={item.volume} min={0} max={2} step={0.05} format={(v) => (v === 0 ? "off" : `${Math.round(v * 100)}%`)} onCommit={(volume) => update({ volume })} />}
      <button type="button" className="small danger" onClick={() => run({ op: "remove_broll", id: item.id })}>
        Remove B-roll
      </button>
    </div>
  );
}

function ClipInspector({ edl }: { edl: Edl }) {
  const seek = useEditor((s) => s.seek);
  return (
    <div className="tab-body inspector">
      <h3>Clip</h3>
      <p className="stage">Select a segment, transition, B-roll or text on the timeline to edit it.</p>
      <div className="row">
        <Slider label="Fade in" value={edl.fade_in} min={0} max={5} step={0.1} format={(v) => `${v.toFixed(1)} s`} onCommit={(fade_in) => run({ op: "update_clip", fade_in })} />
        <Slider label="Fade out" value={edl.fade_out} min={0} max={5} step={0.1} format={(v) => `${v.toFixed(1)} s`} onCommit={(fade_out) => run({ op: "update_clip", fade_out })} />
      </div>
      {edl.markers.length > 0 && (
        <section>
          <h4>Markers</h4>
          <ul className="overlay-list">
            {edl.markers.map((m) => (
              <li key={m.id} className="row">
                <button type="button" className="word" onClick={() => seek(m.time)}>
                  {clock(m.time)} {m.label}
                </button>
                <button type="button" className="small" onClick={() => run({ op: "remove_marker", id: m.id })}>
                  ✕
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section>
        <h4>Shortcuts</h4>
        <dl className="shortcuts">
          {SHORTCUTS.map(([keys, action]) => (
            <div key={keys}>
              <dt>{keys}</dt>
              <dd>{action}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}

function describe(segment: Segment): string {
  if (segment.kind === "image") return `Image · ${segment.image}`;
  if (segment.kind === "freeze") return `Freeze frame · ${clock(segment.at)}`;
  return `${segment.media ? "Other video" : "Clip video"} · ${clock(segment.start)}–${clock(segment.end)}`;
}
