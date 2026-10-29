import { useState } from "react";
import { mediaUrl } from "./api/client";
import type { Clip } from "./api/types";
import { useVideos } from "./api/useVideos";
import { Editor } from "./editor/Editor";
import { ErrorBoundary } from "./ErrorBoundary";
import { ClipsPanel } from "./panels/ClipsPanel";
import { SourcesPanel } from "./panels/SourcesPanel";
import { Timeline } from "./timeline/Timeline";

export function App() {
  const { videos, error, upsert, remove } = useVideos();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedClip, setSelectedClip] = useState<Clip | null>(null);
  const selected = videos.find((v) => v.id === selectedId) ?? null;
  const clip = selectedClip?.video_id === selectedId ? selectedClip : null;

  const selectVideo = (id: string | null) => {
    setSelectedId(id);
    setSelectedClip(null);
  };

  return (
    <div className="app">
      <SourcesPanel
        videos={videos}
        selectedId={selectedId}
        onSelect={selectVideo}
        onAdded={upsert}
        onDeleted={(id) => {
          remove(id);
          if (id === selectedId) selectVideo(null);
        }}
      />
      <main className="panel editor">
        {error && <p className="error">{error}</p>}
        {clip && selected ? (
          <ErrorBoundary key={clip.id} label="Editor">
            <Editor clipId={clip.id} video={selected} />
          </ErrorBoundary>
        ) : (
          <>
            <h2>Editor</h2>
            {/* width is set once normalization has written source.mp4 — minutes into a
                long pipeline — so the video is watchable long before clips exist. */}
            {selected && selected.width != null ? (
              <>
                <video
                  key={selected.id}
                  className="preview"
                  src={mediaUrl(selected.id, "source.mp4")}
                  controls
                  preload="metadata"
                />
                {selected.status === "processing" && (
                  <p className="stage">Still processing — clips will appear on the right when ready.</p>
                )}
              </>
            ) : (
              <p className="placeholder">
                {selected
                  ? "Downloading — the video will play here in a few minutes."
                  : "Select a video, then a clip to edit it here."}
              </p>
            )}
          </>
        )}
      </main>
      <ClipsPanel video={selected} selectedClipId={clip?.id ?? null} onSelect={setSelectedClip} />
      {clip ? (
        <ErrorBoundary key={clip.id} label="Timeline">
          <Timeline />
        </ErrorBoundary>
      ) : (
        <section className="panel timeline">
          <h2>Timeline</h2>
        </section>
      )}
    </div>
  );
}
