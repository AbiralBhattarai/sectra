import { useEffect, useRef, useState } from "react";
import { listVideos, mediaUrl } from "../api/client";
import type { Video } from "../api/types";
import { insertionIndex } from "./actions";
import { run } from "./commands";
import { clock } from "./Preview";
import { useEditor } from "./store";

/** Play any library video, mark an in and out point, and put that stretch into the clip:
 * inserted at the playhead, appended, or laid over it as B-roll. */
export function SourceMonitor({ videoId }: { videoId: string | null }) {
  const clipVideo = useEditor((s) => s.video!);
  const [videos, setVideos] = useState<Video[]>([clipVideo]);
  const [selected, setSelected] = useState(videoId ?? clipVideo.id);
  const [range, setRange] = useState<{ in: number | null; out: number | null }>({ in: null, out: null });
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    listVideos().then((all) => setVideos(all.filter((v) => v.duration != null)), () => undefined);
  }, []);
  useEffect(() => {
    if (videoId) setSelected(videoId);
  }, [videoId]);
  useEffect(() => setRange({ in: null, out: null }), [selected]);

  const now = () => videoRef.current?.currentTime ?? 0;
  const ready = range.in != null && range.out != null && range.out - range.in >= 0.1;
  const media = selected === clipVideo.id ? null : selected;
  const playhead = () => useEditor.getState().playhead;

  return (
    <div
      className="tab-body source-monitor"
      tabIndex={-1}
      onKeyDown={(event) => {
        if (event.key === "i") setRange((r) => ({ ...r, in: now() }));
        if (event.key === "o") setRange((r) => ({ ...r, out: now() }));
      }}
    >
      <select value={selected} onChange={(e) => setSelected(e.target.value)} aria-label="Source video">
        {videos.map((v) => (
          <option key={v.id} value={v.id}>
            {v.title}
            {v.id === clipVideo.id ? " (this clip)" : v.kind === "asset" ? " (B-roll)" : ""}
          </option>
        ))}
      </select>
      <video ref={videoRef} key={selected} className="source-video" src={mediaUrl(selected, "source.mp4")} controls preload="metadata" />
      <div className="row">
        <button type="button" className="small" onClick={() => setRange((r) => ({ ...r, in: now() }))} title="Mark in (I)">
          In {range.in != null ? clock(range.in) : "–"}
        </button>
        <button type="button" className="small" onClick={() => setRange((r) => ({ ...r, out: now() }))} title="Mark out (O)">
          Out {range.out != null ? clock(range.out) : "–"}
        </button>
        {ready && <span className="stage">{clock(range.out! - range.in!)}</span>}
      </div>
      <div className="row">
        <button type="button" disabled={!ready} onClick={() => run({ op: "insert", media, start: range.in!, end: range.out!, at_index: insertionIndex(playhead()) })}>
          Insert at playhead
        </button>
        <button type="button" disabled={!ready} onClick={() => run({ op: "insert", media, start: range.in!, end: range.out! })}>
          Append
        </button>
        <button
          type="button"
          disabled={!ready}
          onClick={() => run({ op: "add_broll", media: selected, start: playhead(), duration: range.out! - range.in!, media_start: range.in! })}
        >
          B-roll at playhead
        </button>
      </div>
    </div>
  );
}
