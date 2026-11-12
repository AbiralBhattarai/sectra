import { useEffect, useState } from "react";
import { run } from "./commands";
import { NumberField } from "./controls";
import { clock } from "./Preview";
import { outputDuration } from "./sequence";
import { useEditor } from "./store";
import type { Overlay, OverlayStyle } from "./types";

const DEFAULT_SECONDS = 3;

export function OverlayEditor() {
  const edl = useEditor((s) => s.edl)!;
  const selection = useEditor((s) => s.selection);
  const { select, seek } = useEditor.getState();
  const selected = selection?.kind === "overlay" ? edl.overlays.find((o) => o.id === selection.id) : undefined;

  const add = async () => {
    const { playhead } = useEditor.getState();
    const total = outputDuration(edl.segments);
    const start = Math.max(0, Math.min(playhead, total - DEFAULT_SECONDS));
    const before = new Set(edl.overlays.map((o) => o.id));
    if (await run({ op: "add_overlay", text: "Your text here", start, end: Math.min(start + DEFAULT_SECONDS, total) })) {
      const added = useEditor.getState().edl!.overlays.find((o) => !before.has(o.id));
      if (added) select({ kind: "overlay", id: added.id });
    }
  };

  return (
    <div className="tab-body">
      <button type="button" onClick={add}>
        Add text at playhead
      </button>
      {selected && <OverlayForm overlay={selected} />}
      <ul className="overlay-list">
        {edl.overlays.map((overlay) => (
          <li key={overlay.id}>
            <button
              type="button"
              className={`word${overlay.id === selected?.id ? " selected" : ""}`}
              onClick={() => {
                select({ kind: "overlay", id: overlay.id });
                seek(overlay.start);
              }}
            >
              <span className="stage">
                {clock(overlay.start)}–{clock(overlay.end)}
              </span>{" "}
              {overlay.text}
            </button>
          </li>
        ))}
      </ul>
      {edl.overlays.length === 0 && <p className="placeholder">Text overlays appear on top of the video, e.g. a hook line.</p>}
    </div>
  );
}

export function OverlayForm({ overlay }: { overlay: Overlay }) {
  const [text, setText] = useState(overlay.text);
  useEffect(() => setText(overlay.text), [overlay]);
  const update = (fields: Partial<Overlay>) => run({ op: "update_overlay", id: overlay.id, ...fields });

  return (
    <div className="word-form">
      <input
        value={text}
        onChange={(event) => setText(event.target.value)}
        onBlur={() => text.trim() && text !== overlay.text && update({ text })}
        onKeyDown={(event) => event.key === "Enter" && (event.target as HTMLInputElement).blur()}
        maxLength={200}
        aria-label="Overlay text"
      />
      <select value={overlay.style} onChange={(event) => update({ style: event.target.value as OverlayStyle })} aria-label="Overlay style">
        <option value="title">Title</option>
        <option value="label">Label</option>
      </select>
      <div className="row">
        <NumberField label="Start (s)" value={overlay.start} min={0} onCommit={(start) => update({ start })} />
        <NumberField label="End (s)" value={overlay.end} min={0} onCommit={(end) => update({ end })} />
      </div>
      <p className="stage">Drag the text on the preview to move it, or its block on the timeline to retime it.</p>
      <button type="button" className="danger" onClick={() => run({ op: "remove_overlay", id: overlay.id })}>
        Delete text
      </button>
    </div>
  );
}
