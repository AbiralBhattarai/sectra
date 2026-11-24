import { useState } from "react";
import { CaptionEditor } from "./CaptionEditor";
import { CharacterEditor } from "./CharacterEditor";
import { ExportPanel } from "./ExportPanel";
import { MusicEditor } from "./MusicEditor";
import { OverlayEditor } from "./OverlayEditor";
import { useEditor } from "./store";
import { ZoomEditor } from "./ZoomEditor";

const TABS = {
  captions: "Captions",
  narrator: "Narrator",
  overlays: "Text",
  zooms: "Zoom",
  music: "Music",
  export: "Export",
} as const;
type Tab = keyof typeof TABS;

export function SidePanel() {
  const [tab, setTab] = useState<Tab>("captions");
  const overlayCount = useEditor((s) => s.edl?.overlays.length ?? 0);
  const hasMusic = useEditor((s) => s.edl?.music != null);
  const zoomCount = useEditor((s) => s.edl?.zooms.length ?? 0);
  const hasNarrator = useEditor((s) => s.edl?.character != null);
  // The Narrator tab only exists for clips that have a narrator (stories).
  const tabs = (Object.keys(TABS) as Tab[]).filter((key) => key !== "narrator" || hasNarrator);

  return (
    <aside className="side-panel">
      <nav className="tabs" role="tablist">
        {tabs.map((key) => (
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
      {tab === "narrator" && hasNarrator && <CharacterEditor />}
      {tab === "overlays" && <OverlayEditor />}
      {tab === "zooms" && <ZoomEditor />}
      {tab === "music" && <MusicEditor />}
      {tab === "export" && <ExportPanel />}
    </aside>
  );
}
