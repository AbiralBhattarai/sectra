import { useMemo, useRef, useState, type PointerEvent } from "react";
import { characterUrl } from "../api/client";
import { blinkStarts, characterBox, characterState } from "./character";
import { OUTPUT_SIZES } from "./crop";
import { clamp } from "./edlOps";
import { useEditor } from "./store";
import { EMOTIONS } from "./types";

const MOUTHS = ["A", "B", "C", "D", "E", "F", "G", "H", "X"];

/** The talking narrator over the preview, as the render draws it: every layer is
 * mounted once (no flicker while the mouth changes) and only the current ones show.
 * Drag it to move it (one undo step per drag). */
export function CharacterLayer() {
  const track = useEditor((s) => s.edl?.character);
  const aspect = useEditor((s) => s.edl?.aspect ?? "9:16");
  const lastEnd = useEditor((s) => s.edl?.ranges[s.edl.ranges.length - 1]?.end ?? 0);
  const cues = useEditor((s) => s.mouthCues);
  const playhead = useEditor((s) => s.playhead);
  const { edit } = useEditor.getState();
  const [draft, setDraft] = useState<{ x: number; y: number } | null>(null);
  const drag = useRef<{ startX: number; startY: number; x: number; y: number; frame: DOMRect } | null>(null);
  const blinks = useMemo(() => blinkStarts(lastEnd + 1), [lastEnd]);

  if (!track || !track.enabled) return null;
  const position = draft ? { ...track, ...draft } : track;
  const [outWidth, outHeight] = OUTPUT_SIZES[aspect];
  const [x, y, width, height] = characterBox(aspect, position);
  const state = characterState(cues, track.moods, blinks, playhead);
  const layer = (path: string) => characterUrl(track.name, path);

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.stopPropagation(); // don't pan the crop
    event.currentTarget.setPointerCapture(event.pointerId);
    const frame = event.currentTarget.parentElement!.getBoundingClientRect();
    drag.current = { startX: event.clientX, startY: event.clientY, x: track.x, y: track.y, frame };
  };
  const onPointerMove = (event: PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    setDraft({
      x: clamp(d.x + (event.clientX - d.startX) / d.frame.width, 0, 1),
      y: clamp(d.y + (event.clientY - d.startY) / d.frame.height, 0, 1),
    });
  };
  const onPointerUp = () => {
    if (draft) edit((e) => (e.character ? { ...e, character: { ...e.character, ...draft } } : e));
    drag.current = null;
    setDraft(null);
  };

  return (
    <div
      className="character"
      style={{
        left: `${(x / outWidth) * 100}%`,
        top: `${(y / outHeight) * 100}%`,
        width: `${(width / outWidth) * 100}%`,
        height: `${(height / outHeight) * 100}%`,
      }}
      title="Drag to move the narrator"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
    >
      <div className="character-body" style={{ transform: `translateY(${state.bob * 100}%)` }}>
        {EMOTIONS.map((emotion) => (
          <img
            key={emotion}
            src={layer(`base/${emotion}.svg`)}
            alt=""
            draggable={false}
            style={{ visibility: emotion === state.expression ? "visible" : "hidden" }}
          />
        ))}
        {MOUTHS.map((shape) => (
          <img
            key={shape}
            src={layer(`mouth/${shape}.svg`)}
            alt=""
            draggable={false}
            style={{ visibility: shape === state.mouth ? "visible" : "hidden" }}
          />
        ))}
        <img
          src={layer("blink.svg")}
          alt=""
          draggable={false}
          style={{ visibility: state.blink ? "visible" : "hidden" }}
        />
      </div>
    </div>
  );
}
