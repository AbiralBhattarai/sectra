import { useCallback, useEffect, useState } from "react";
import { imageUrl, listImages, listVideos, mediaUrl, uploadImage, uploadVideo } from "../api/client";
import type { Video } from "../api/types";
import { useJobEvents } from "../api/useJobEvents";
import { MEDIA_MIME, type DraggedMedia } from "../timeline/Timeline";
import { insertionIndex } from "./actions";
import { run } from "./commands";
import { clock } from "./Preview";
import { useEditor } from "./store";
import type { ImageAsset } from "./types";

/** Videos (assets and other sources) and images to edit in: drag one onto the Video or
 * B-roll lane, or use the buttons. Long source videos are better cut in the Source tab. */
export function MediaBin({ onOpenSource }: { onOpenSource: (videoId: string) => void }) {
  const clipVideo = useEditor((s) => s.video!.id);
  const [videos, setVideos] = useState<Video[]>([]);
  const [images, setImages] = useState<ImageAsset[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [upload, setUpload] = useState<string | null>(null);

  const refresh = useCallback(() => {
    listVideos().then(setVideos, (e: Error) => setError(e.message));
    listImages().then(setImages, (e: Error) => setError(e.message));
  }, []);
  useEffect(refresh, [refresh]);
  useJobEvents((event) => {
    if (event.video_id && videos.some((v) => v.id === event.video_id) && (event.status === "succeeded" || event.status === "failed")) refresh();
  });

  const send = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    try {
      if (file.type.startsWith("image/")) {
        setUpload("Uploading image…");
        await uploadImage(file);
      } else {
        await uploadVideo(file, (f) => setUpload(`Uploading ${Math.round(f * 100)}%`), "asset");
      }
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUpload(null);
    }
  };

  const assets = videos.filter((v) => v.kind === "asset");
  const sources = videos.filter((v) => v.kind === "source");
  return (
    <div className="tab-body media-bin">
      <label className="button">
        {upload ?? "Upload video or image"}
        <input type="file" accept="video/*,image/png,image/jpeg,image/webp" hidden disabled={!!upload} onChange={(e) => {
          void send(e.target.files?.[0]);
          e.target.value = "";
        }} />
      </label>
      <p className="stage">Uploaded videos are B-roll assets: prepared for editing, not transcribed.</p>
      {error && <p className="error">{error}</p>}

      <h4>B-roll videos</h4>
      {assets.length === 0 && <p className="placeholder">None yet.</p>}
      {assets.map((v) => <VideoItem key={v.id} video={v} cap={60} />)}

      <h4>Images</h4>
      {images.length === 0 && <p className="placeholder">None yet.</p>}
      {images.map((image) => (
        <MediaItem
          key={image.file}
          thumb={<img src={imageUrl(image.file)} alt="" />}
          title={image.name}
          media={{ kind: "image", file: image.file }}
          onInsert={(at) => run({ op: "insert_image", image: image.file, duration: 3, at_index: at })}
          onBroll={(t) => run({ op: "add_broll", image: image.file, start: t, duration: 3 })}
        />
      ))}

      <h4>Source videos</h4>
      {sources.map((v) => (
        <div key={v.id} className="media-item">
          <img className="thumb" src={mediaUrl(v.id, "thumbnail.jpg")} alt="" />
          <div className="media-meta">
            <span>{v.title}{v.id === clipVideo && " (this clip)"}</span>
            <button type="button" className="small" onClick={() => onOpenSource(v.id)}>
              Pick a range…
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function VideoItem({ video, cap }: { video: Video; cap: number }) {
  const ready = video.status === "ready" && video.duration != null;
  const length = Math.min(video.duration ?? 0, cap);
  return (
    <MediaItem
      thumb={<img className="thumb" src={mediaUrl(video.id, "thumbnail.jpg")} alt="" />}
      title={`${video.title}${video.duration ? ` · ${clock(video.duration)}` : ""}`}
      status={ready ? undefined : video.status === "failed" ? "failed" : "processing…"}
      media={ready ? { kind: "video", id: video.id, duration: length } : null}
      onInsert={(at) => run({ op: "insert", media: video.id, start: 0, end: length, at_index: at })}
      onBroll={(t) => run({ op: "add_broll", media: video.id, start: t, duration: Math.min(length, 3) })}
    />
  );
}

function MediaItem(props: {
  thumb: React.ReactNode;
  title: string;
  status?: string;
  media: DraggedMedia | null;
  onInsert: (atIndex: number) => unknown;
  onBroll: (t: number) => unknown;
}) {
  const playhead = () => useEditor.getState().playhead;
  return (
    <div
      className="media-item"
      draggable={!!props.media}
      onDragStart={(event) => {
        event.dataTransfer.setData(MEDIA_MIME, JSON.stringify(props.media));
        event.dataTransfer.effectAllowed = "copy";
      }}
      title={props.media ? "Drag onto the Video or B-roll lane" : undefined}
    >
      {props.thumb}
      <div className="media-meta">
        <span>{props.title}</span>
        {props.status ? (
          <span className="stage">{props.status}</span>
        ) : (
          <span className="row">
            <button type="button" className="small" onClick={() => props.onInsert(insertionIndex(playhead()))}>
              Insert
            </button>
            <button type="button" className="small" onClick={() => props.onBroll(playhead())}>
              B-roll
            </button>
          </span>
        )}
      </div>
    </div>
  );
}
