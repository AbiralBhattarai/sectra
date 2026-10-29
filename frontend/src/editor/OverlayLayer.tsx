import { useRef, useState, type PointerEvent } from "react";
import { clamp, overlaysAt, sourceToOutput } from "./edlOps";
import { useEditor } from "./store";

/** Text overlays on the preview; drag one to move it (one undo step per drag). */
export function OverlayLayer() {
  const edl = useEditor((s) => s.edl)!;
  const playhead = useEditor((s) => s.playhead);
  const selected = useEditor((s) => s.selectedOverlay);
  const { edit, selectOverlay } = useEditor.getState();
  const [draft, setDraft] = useState<{ index: number; x: number; y: number } | null>(null);
  const drag = useRef<{ index: number; startX: number; startY: number; x: number; y: number; frame: DOMRect } | null>(null);

  const visible = overlaysAt(edl.overlays, sourceToOutput(playhead, edl.ranges));

  const onPointerDown = (event: PointerEvent<HTMLDivElement>, index: number) => {
    event.stopPropagation(); // don't pan the crop
    event.currentTarget.setPointerCapture(event.pointerId);
    selectOverlay(index);
    const overlay = edl.overlays[index];
    const frame = event.currentTarget.parentElement!.getBoundingClientRect();
    drag.current = { index, startX: event.clientX, startY: event.clientY, x: overlay.x, y: overlay.y, frame };
  };
  const onPointerMove = (event: PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    setDraft({
      index: d.index,
      x: clamp(d.x + (event.clientX - d.startX) / d.frame.width, 0, 1),
      y: clamp(d.y + (event.clientY - d.startY) / d.frame.height, 0, 1),
    });
  };
  const onPointerUp = () => {
    if (draft) {
      edit((e) => ({
        ...e,
        overlays: e.overlays.map((o, i) => (i === draft.index ? { ...o, x: draft.x, y: draft.y } : o)),
      }));
    }
    drag.current = null;
    setDraft(null);
  };

  return (
    <>
      {visible.map((index) => {
        const overlay = edl.overlays[index];
        const position = draft?.index === index ? draft : overlay;
        return (
          <div
            key={index}
            className={`overlay overlay-${overlay.style}${index === selected ? " selected" : ""}`}
            style={{ left: `${position.x * 100}%`, top: `${position.y * 100}%` }}
            onPointerDown={(event) => onPointerDown(event, index)}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
          >
            {overlay.text}
          </div>
        );
      })}
    </>
  );
}
