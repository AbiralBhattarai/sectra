import { useState } from "react";
import { autoZoom } from "../api/client";
import { addZoom, updateZoom } from "./crop";
import { clamp } from "./edlOps";
import { clock } from "./Preview";
import { useEditor } from "./store";
import type { Zoom } from "./types";

/** Zoom-ins: generate them (hook push, sentence punches, loud moments, payoff), or add
 * and tune them by hand. Times are source time, shown like the timeline. */
export function ZoomEditor() {
  const clip = useEditor((s) => s.clip)!;
  const edl = useEditor((s) => s.edl)!;
  const selected = useEditor((s) => s.selectedZoom);
  const { edit, selectZoom, seek } = useEditor.getState();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const clipEnd = edl.ranges[edl.ranges.length - 1].end;

  const generate = async () => {
    setError(null);
    setBusy(true);
    try {
      const zooms = await autoZoom(clip.id, edl.ranges);
      edit((e) => ({ ...e, zooms }));
      selectZoom(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const add = () => {
    const { playhead } = useEditor.getState();
    const next = addZoom(edl, playhead, clipEnd);
    if (!next) {
      setError("No room for a zoom at the playhead (one is already there, or the clip ends).");
      return;
    }
    setError(null);
    edit(() => next);
    selectZoom(next.zooms.findIndex((z) => z.start === Math.round(playhead * 1000) / 1000));
  };

  return (
    <div className="tab-body">
      <div className="downloads">
        <button type="button" onClick={generate} disabled={busy}>
          {busy ? "Generating…" : edl.zooms.length ? "Auto zoom again" : "Auto zoom"}
        </button>
        <button type="button" onClick={add}>
          Add at playhead
        </button>
        {edl.zooms.length > 0 && (
          <button
            type="button"
            className="danger"
            onClick={() => {
              edit((e) => ({ ...e, zooms: [] }));
              selectZoom(null);
            }}
          >
            Clear
          </button>
        )}
      </div>
      {edl.split_screen && !edl.tracking?.enabled && (
        <p className="stage">Zooms are ignored while the split screen is on.</p>
      )}
      {error && <p className="error">{error}</p>}
      {selected != null && edl.zooms[selected] && <ZoomForm index={selected} zoom={edl.zooms[selected]} />}
      <ul className="overlay-list">
        {edl.zooms.map((zoom, index) => (
          <li key={`${zoom.start}-${index}`}>
            <button
              type="button"
              className={`word${index === selected ? " selected" : ""}`}
              onClick={() => {
                selectZoom(index);
                seek(zoom.start);
              }}
            >
              <span className="stage">
                {clock(zoom.start)}–{clock(zoom.end)}
              </span>{" "}
              ×{zoom.scale.toFixed(2)} {zoom.ramp > 0 ? "push" : "punch"}
            </button>
          </li>
        ))}
      </ul>
      {edl.zooms.length === 0 && (
        <p className="placeholder">
          Zoom-ins keep a vertical clip moving: a push on the hook, punches on sentence changes and loud
          moments. Auto zoom places them for you.
        </p>
      )}
    </div>
  );
}

function ZoomForm({ index, zoom }: { index: number; zoom: Zoom }) {
  const { edit, selectZoom } = useEditor.getState();
  const update = (patch: Partial<Zoom>) => edit((e) => updateZoom(e, index, patch));
  const nudge = (field: "start" | "end", delta: number) => update({ [field]: zoom[field] + delta });
  const length = zoom.end - zoom.start;

  return (
    <div className="word-form">
      <label className="zoom">
        ×{zoom.scale.toFixed(2)}
        <input
          type="range"
          min={1.05}
          max={1.6}
          step={0.05}
          value={zoom.scale}
          onChange={(event) => update({ scale: Number(event.target.value) })}
          aria-label="Zoom amount"
        />
      </label>
      <select
        value={zoom.ramp > 0 ? "push" : "punch"}
        onChange={(event) =>
          update({ ramp: event.target.value === "push" ? clamp(Math.round(length * 5) / 10, 0.3, 2) : 0 })
        }
        aria-label="Zoom style"
      >
        <option value="punch">Punch-in (instant)</option>
        <option value="push">Push-in (smooth)</option>
      </select>
      {(["start", "end"] as const).map((field) => (
        <div className="nudge" key={field}>
          <span>{field}</span>
          <button type="button" onClick={() => nudge(field, -0.1)}>
            −
          </button>
          <span className="timecode">{clock(zoom[field])}</span>
          <button type="button" onClick={() => nudge(field, 0.1)}>
            +
          </button>
        </div>
      ))}
      <p className="stage">Drag the zoom’s edges on the timeline to retime it.</p>
      <button
        type="button"
        className="danger"
        onClick={() => {
          edit((e) => ({ ...e, zooms: e.zooms.filter((_, i) => i !== index) }));
          selectZoom(null);
        }}
      >
        Delete zoom
      </button>
    </div>
  );
}
