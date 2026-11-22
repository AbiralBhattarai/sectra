import { useState } from "react";
import { CaptionEditor } from "./CaptionEditor";
import { ExportPanel } from "./ExportPanel";
import { MusicEditor } from "./MusicEditor";
import { OverlayEditor } from "./OverlayEditor";
import { useEditor } from "./store";
import { ZoomEditor } from "./ZoomEditor";

const TABS = { captions: "Captions", overlays: "Text", zooms: "Zoom", music: "Music", export: "Export" } as const;
type Tab = keyof typeof TABS;

export function SidePanel() {
  const [tab, setTab] = useState<Tab>("captions");
  const overlayCount = useEditor((s) => s.edl?.overlays.length ?? 0);
  const hasMusic = useEditor((s) => s.edl?.music != null);
  const zoomCount = useEditor((s) => s.edl?.zooms.length ?? 0);

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
            {key === "zooms" && zoomCount > 0 && ` (${zoomCount})`}
            {key === "music" && hasMusic && " ♪"}
          </button>
        ))}
      </nav>
      {tab === "captions" && <CaptionEditor />}
      {tab === "overlays" && <OverlayEditor />}
      {tab === "zooms" && <ZoomEditor />}
      {tab === "music" && <MusicEditor />}
      {tab === "export" && <ExportPanel />}
    </aside>
  );
}
