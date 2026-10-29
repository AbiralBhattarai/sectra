import { useEffect, useState } from "react";
import { clamp, newOverlay, outputDuration, outputToSource, sourceToOutput } from "./edlOps";
import { clock } from "./Preview";
import { useEditor } from "./store";
import type { Overlay, OverlayStyle } from "./types";

export function OverlayEditor() {
  const edl = useEditor((s) => s.edl)!;
  const selected = useEditor((s) => s.selectedOverlay);
  const { edit, selectOverlay, seek } = useEditor.getState();

  const focus = (index: number, overlay: Overlay) => {
    selectOverlay(index);
    seek(outputToSource(overlay.start, edl.ranges));
  };

  const add = () => {
    const { playhead } = useEditor.getState();
    const overlay = newOverlay(sourceToOutput(playhead, edl.ranges), outputDuration(edl.ranges));
    edit((e) => ({ ...e, overlays: [...e.overlays, overlay] }));
    focus(edl.overlays.length, overlay);
  };

  return (
    <div className="tab-body">
      <button type="button" onClick={add}>
        Add text at playhead
      </button>
      {selected != null && edl.overlays[selected] && (
        <OverlayForm index={selected} overlay={edl.overlays[selected]} />
      )}
      <ul className="overlay-list">
        {edl.overlays.map((overlay, index) => (
          <li key={index}>
            <button
              type="button"
              className={`word${index === selected ? " selected" : ""}`}
              onClick={() => focus(index, overlay)}
            >
              <span className="stage">
                {clock(overlay.start)}–{clock(overlay.end)}
              </span>{" "}
              {overlay.text}
            </button>
          </li>
        ))}
      </ul>
      {edl.overlays.length === 0 && (
        <p className="placeholder">Text overlays appear on top of the video, e.g. a hook line.</p>
      )}
    </div>
  );
}

function OverlayForm({ index, overlay }: { index: number; overlay: Overlay }) {
  const total = useEditor((s) => outputDuration(s.edl!.ranges));
  const { edit, selectOverlay } = useEditor.getState();
  const [text, setText] = useState(overlay.text);
  useEffect(() => setText(overlay.text), [overlay]);

  const update = (patch: Partial<Overlay>) =>
    edit((e) => {
      const next = { ...overlay, ...patch };
      if (!next.text.trim() || next.end - next.start < 0.1) return e;
      return { ...e, overlays: e.overlays.map((o, i) => (i === index ? next : o)) };
    });
  const nudge = (field: "start" | "end", delta: number) =>
    update({ [field]: Math.round(clamp(overlay[field] + delta, 0, total) * 10) / 10 });

  return (
    <div className="word-form">
      <input
        value={text}
        onChange={(event) => setText(event.target.value)}
        onBlur={() => text !== overlay.text && update({ text })}
        onKeyDown={(event) => event.key === "Enter" && (event.target as HTMLInputElement).blur()}
        maxLength={200}
        aria-label="Overlay text"
      />
      <select
        value={overlay.style}
        onChange={(event) => update({ style: event.target.value as OverlayStyle })}
        aria-label="Overlay style"
      >
        <option value="title">Title</option>
        <option value="label">Label</option>
      </select>
      {(["start", "end"] as const).map((field) => (
        <div className="nudge" key={field}>
          <span>{field}</span>
          <button type="button" onClick={() => nudge(field, -0.1)}>−</button>
          <span className="timecode">{clock(overlay[field])}</span>
          <button type="button" onClick={() => nudge(field, 0.1)}>+</button>
        </div>
      ))}
      <p className="stage">Drag the text on the preview to move it.</p>
      <button
        type="button"
        className="danger"
        onClick={() => {
          edit((e) => ({ ...e, overlays: e.overlays.filter((_, i) => i !== index) }));
          selectOverlay(null);
        }}
      >
        Delete text
      </button>
    </div>
  );
}
