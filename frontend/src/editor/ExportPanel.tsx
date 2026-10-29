import { useCallback, useEffect, useState } from "react";
import { listExports, requestExport } from "../api/client";
import type { Export } from "../api/types";
import { useJobEvents } from "../api/useJobEvents";
import { useEditor } from "./store";

export function ExportPanel() {
  const clip = useEditor((s) => s.clip)!;
  const saveState = useEditor((s) => s.saveState);
  const [exports, setExports] = useState<Export[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(
    () => listExports(clip.id).then(setExports, (e: Error) => setError(e.message)),
    [clip.id],
  );
  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Live progress; refetch on completion for the download links.
  useJobEvents((event) => {
    if (event.clip_id !== clip.id) return;
    setExports((current) =>
      current.map((e) => (e.id === event.job_id ? { ...e, status: event.status, progress: event.progress, error: event.error } : e)),
    );
    if (event.status === "succeeded" || event.status === "failed") void refresh();
  });

  const start = async () => {
    setError(null);
    try {
      const created = await requestExport(clip.id);
      setExports((current) => [created, ...current]);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const saved = saveState === "saved";
  return (
    <div className="tab-body">
      <button type="button" onClick={start} disabled={!saved}>
        Export MP4 + captions
      </button>
      {!saved && <p className="stage">Waiting for your latest edits to save…</p>}
      {error && <p className="error">{error}</p>}
      <ul className="export-list">
        {exports.map((e) => (
          <li key={e.id} className="word-form">
            <div className="clip-row">
              <span className="stage">{new Date(e.created_at).toLocaleTimeString()}</span>
              {e.status === "succeeded" && new Date(e.created_at) < new Date(clip.updated_at) && (
                <span className="stage" title="The clip was edited after this export">
                  outdated
                </span>
              )}
            </div>
            {(e.status === "queued" || e.status === "running") && (
              <>
                <span className="stage">{e.status === "queued" ? "Waiting to render" : `Rendering · ${Math.round(e.progress * 100)}%`}</span>
                <progress value={e.progress} max={1} />
              </>
            )}
            {e.status === "failed" && <span className="error">{e.error ?? "Render failed"}</span>}
            {e.status === "succeeded" && e.video_url && e.subtitles_url && (
              <div className="downloads">
                <a className="button" href={e.video_url} download>
                  Download MP4
                </a>
                <a href={e.subtitles_url} download>
                  .srt
                </a>
              </div>
            )}
          </li>
        ))}
      </ul>
      {exports.length === 0 && <p className="placeholder">Renders the clip at 1080p with captions and overlays burned in.</p>}
    </div>
  );
}
