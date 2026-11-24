import { useMemo } from "react";
import { pageAt, paginate } from "./captions";
import { useEditor } from "./store";

/** Captions as they'll be burned in, positioned and sized relative to the frame. */
export function CaptionOverlay() {
  const captions = useEditor((s) => s.edl?.captions);
  const playhead = useEditor((s) => s.playhead);
  const pages = useMemo(() => (captions ? paginate(captions.words, captions.style) : []), [captions]);
  const page = pageAt(pages, playhead);
  if (!captions || !page) return null;
  // The word being spoken: the last one that has started.
  const active = page.words.reduce((last, word, index) => (playhead >= word.start ? index : last), -1);

  return (
    <div
      className={`caption-layer caption-${captions.style}`}
      // A set y anchors the block's bottom edge there (e.g. above a narrator), as the render does.
      style={captions.y != null ? { alignItems: "flex-end", paddingTop: 0, paddingBottom: `${(1 - captions.y) * 100}cqh` } : undefined}
    >
      <span className="caption-text">
        {page.words.map((word, index) => (
          <span key={index} className={index === active ? "active" : undefined}>
            {word.text}{" "}
          </span>
        ))}
      </span>
    </div>
  );
}
