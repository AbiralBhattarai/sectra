import { useRef, useState, type PointerEvent } from "react";
import { run } from "./commands";
import { clamp } from "./sequence";
import { useEditor } from "./store";

/** Text overlays on the preview; drag one to move it (one edit per drag). */
export function OverlayLayer() {
  const overlays = useEditor((s) => s.edl!.overlays);
  const playhead = useEditor((s) => s.playhead);
  const selection = useEditor((s) => s.selection);
  const select = useEditor((s) => s.select);
  const [draft, setDraft] = useState<{ id: string; x: number; y: number } | null>(null);
  const drag = useRef<{ id: string; startX: number; startY: number; x: number; y: number; frame: DOMRect } | null>(null);

  const onPointerDown = (event: PointerEvent<HTMLDivElement>, id: string) => {
    event.stopPropagation(); // don't pan the crop
    event.currentTarget.setPointerCapture(event.pointerId);
    select({ kind: "overlay", id });
    const overlay = overlays.find((o) => o.id === id)!;
    const frame = event.currentTarget.parentElement!.getBoundingClientRect();
    drag.current = { id, startX: event.clientX, startY: event.clientY, x: overlay.x, y: overlay.y, frame };
  };
  const onPointerMove = (event: PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    setDraft({
      id: d.id,
      x: clamp(d.x + (event.clientX - d.startX) / d.frame.width, 0, 1),
      y: clamp(d.y + (event.clientY - d.startY) / d.frame.height, 0, 1),
    });
  };
  const onPointerUp = () => {
    drag.current = null;
    if (!draft) return;
    void run({ op: "update_overlay", id: draft.id, x: draft.x, y: draft.y }).finally(() => setDraft(null));
  };

  return (
    <>
      {overlays
        .filter((o) => playhead >= o.start && playhead < o.end)
        .map((overlay) => {
          const position = draft?.id === overlay.id ? draft : overlay;
          const selected = selection?.kind === "overlay" && selection.id === overlay.id;
          return (
            <div
              key={overlay.id}
              className={`overlay overlay-${overlay.style}${selected ? " selected" : ""}`}
              style={{ left: `${position.x * 100}%`, top: `${position.y * 100}%` }}
              onPointerDown={(event) => onPointerDown(event, overlay.id)}
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
