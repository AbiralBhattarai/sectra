import { useEffect, useLayoutEffect, useRef, useState } from "react";

export interface MenuItem {
  label: string;
  action: () => unknown;
  disabled?: boolean;
}

/** A right-click menu at (x, y); closes on any outside click or Escape. */
export function ContextMenu({ x, y, items, onClose }: { x: number; y: number; items: (MenuItem | "-")[]; onClose: () => void }) {
  const ref = useRef<HTMLUListElement>(null);
  // Keep the menu on screen (the timeline sits at the bottom of the window).
  const [position, setPosition] = useState({ left: x, top: y });
  useLayoutEffect(() => {
    const { width, height } = ref.current!.getBoundingClientRect();
    setPosition({ left: Math.min(x, innerWidth - width - 4), top: Math.max(4, Math.min(y, innerHeight - height - 4)) });
  }, [x, y]);
  useEffect(() => {
    const close = () => onClose();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("pointerdown", close);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", close);
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <ul ref={ref} className="context-menu" style={position} onPointerDown={(event) => event.stopPropagation()}>
      {items.map((item, i) =>
        item === "-" ? (
          <li key={i} className="separator" />
        ) : (
          <li key={i}>
            <button
              type="button"
              disabled={item.disabled}
              onClick={() => {
                onClose();
                void item.action();
              }}
            >
              {item.label}
            </button>
          </li>
        ),
      )}
    </ul>
  );
}
