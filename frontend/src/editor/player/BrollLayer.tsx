import { imageUrl, mediaUrl } from "../../api/client";
import { clamp } from "../sequence";
import { useEditor } from "../store";
import type { BrollItem } from "../types";
import { brollVideos } from "./elements";

/** B-roll on top of the main track: full frame (cover) or picture-in-picture, faded in
 * and out. Mounted a second early so the video is ready when it appears. */
export function BrollLayer({ frame }: { frame: { width: number; height: number } }) {
  const broll = useEditor((s) => s.edl!.broll);
  const playhead = useEditor((s) => s.playhead);
  const mediaSizes = useEditor((s) => s.mediaSizes);
  const noteMediaSize = useEditor((s) => s.noteMediaSize);
  const selection = useEditor((s) => s.selection);

  return (
    <>
      {broll
        .filter((item) => playhead >= item.start - 1 && playhead < item.start + item.duration)
        .map((item) => {
          const key = item.image ? `image:${item.image}` : item.media!;
          const size = mediaSizes[key];
          const visible = playhead >= item.start;
          const style = { ...box(item, frame, size), opacity: visible ? fadeOpacity(item, playhead) : 0 };
          const className = `broll broll-${item.layout}${selection?.kind === "broll" && selection.id === item.id ? " selected" : ""}`;
          const note = (width: number, height: number) => noteMediaSize(key, { width, height });
          return item.image ? (
            <img
              key={item.id}
              className={className}
              style={style}
              src={imageUrl(item.image)}
              alt=""
              onLoad={(e) => note(e.currentTarget.naturalWidth, e.currentTarget.naturalHeight)}
            />
          ) : (
            <video
              key={item.id}
              ref={(element) => {
                if (element) brollVideos.set(item.id, element);
                else brollVideos.delete(item.id);
              }}
              className={className}
              style={style}
              src={mediaUrl(item.media!, "source.mp4")}
              preload="auto"
              playsInline
              onLoadedMetadata={(e) => note(e.currentTarget.videoWidth, e.currentTarget.videoHeight)}
            />
          );
        })}
    </>
  );
}

/** Where the item lands in the frame (render_planning._plan_broll). */
function box(item: BrollItem, frame: { width: number; height: number }, size?: { width: number; height: number }) {
  if (item.layout === "full") return { left: 0, top: 0, width: frame.width, height: frame.height };
  const width = item.size * frame.width;
  const height = width * (size ? size.height / size.width : 9 / 16);
  return {
    left: clamp(item.x * frame.width - width / 2, 0, frame.width - width),
    top: clamp(item.y * frame.height - height / 2, 0, Math.max(frame.height - height, 0)),
    width,
    height,
  };
}

function fadeOpacity(item: BrollItem, t: number): number {
  if (item.fade <= 0) return 1;
  const local = t - item.start;
  return clamp(Math.min(local / item.fade, (item.duration - local) / item.fade), 0, 1);
}
