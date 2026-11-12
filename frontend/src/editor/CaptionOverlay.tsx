import { useMemo } from "react";
import { captionCues, cueAt } from "./sequence";
import { useEditor } from "./store";

/** Captions as they'll be burned in, positioned and sized relative to the frame. */
export function CaptionOverlay() {
  const edl = useEditor((s) => s.edl);
  const playhead = useEditor((s) => s.playhead);
  const cues = useMemo(() => (edl ? captionCues(edl, edl.captions.style) : []), [edl]);
  const cue = cueAt(cues, playhead);
  if (!edl || !cue) return null;
  // The word being spoken: the last one that has started.
  const active = cue.words.reduce((last, word, index) => (playhead >= word.start ? index : last), -1);

  return (
    <div className={`caption-layer caption-${edl.captions.style}`}>
      <span className="caption-text">
        {cue.words.map((word, index) => (
          <span key={index} className={index === active ? "active" : undefined}>
            {word.text}{" "}
          </span>
        ))}
      </span>
    </div>
  );
}
