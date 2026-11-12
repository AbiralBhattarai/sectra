import { useEffect, useState } from "react";
import { CaptionEditor } from "./CaptionEditor";
import { ExportPanel } from "./ExportPanel";
import { Inspector } from "./Inspector";
import { MediaBin } from "./MediaBin";
import { MusicEditor } from "./MusicEditor";
import { OverlayEditor } from "./OverlayEditor";
import { SourceMonitor } from "./SourceMonitor";
import { useEditor } from "./store";

const TABS = {
  inspect: "Edit",
  media: "Media",
  source: "Source",
  captions: "Captions",
  overlays: "Text",
  music: "Music",
  export: "Export",
} as const;
type Tab = keyof typeof TABS;

export function SidePanel() {
  const [tab, setTab] = useState<Tab>("inspect");
  const [sourceVideo, setSourceVideo] = useState<string | null>(null);
  const selection = useEditor((s) => s.selection);
  const overlayCount = useEditor((s) => s.edl?.overlays.length ?? 0);
  const hasMusic = useEditor((s) => s.edl?.music != null);

  // Selecting something on the timeline shows its properties.
  useEffect(() => {
    if (selection && selection.kind !== "overlay") setTab("inspect");
  }, [selection]);

  return (
    <aside className="side-panel">
      <nav className="tabs" role="tablist">
        {(Object.keys(TABS) as Tab[]).map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            className={tab === key ? "active" : undefined}
            onClick={() => setTab(key)}
          >
            {TABS[key]}
            {key === "overlays" && overlayCount > 0 && ` (${overlayCount})`}
            {key === "music" && hasMusic && " ♪"}
          </button>
        ))}
      </nav>
      {tab === "inspect" && <Inspector />}
      {tab === "media" && (
        <MediaBin
          onOpenSource={(id) => {
            setSourceVideo(id);
            setTab("source");
          }}
        />
      )}
      {tab === "source" && <SourceMonitor videoId={sourceVideo} />}
      {tab === "captions" && <CaptionEditor />}
      {tab === "overlays" && <OverlayEditor />}
      {tab === "music" && <MusicEditor />}
      {tab === "export" && <ExportPanel />}
    </aside>
  );
}
