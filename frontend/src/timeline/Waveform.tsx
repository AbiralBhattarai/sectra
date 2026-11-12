import { useEffect, useMemo, useRef } from "react";
import type { Peaks } from "../editor/types";

/** The waveform of source `from`..`to` squeezed into `width` pixels. */
export function Waveform({ peaks, from, to, width }: { peaks: Peaks; from: number; to: number; width: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // reduce, not Math.max(...peaks): a long video has more samples than the stack allows arguments.
  const maxPeak = useMemo(() => peaks.peaks.reduce((m, v) => Math.max(m, v), 0.01), [peaks]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || width < 1) return;
    const ratio = window.devicePixelRatio || 1;
    const height = canvas.clientHeight;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    const context = canvas.getContext("2d")!;
    context.scale(ratio, ratio);
    context.clearRect(0, 0, width, height);
    context.fillStyle = getComputedStyle(canvas).color;
    const perPixel = (to - from) / width;
    for (let px = 0; px < width; px++) {
      const a = Math.floor((from + px * perPixel) * peaks.per_second);
      const b = Math.max(a + 1, Math.ceil((from + (px + 1) * perPixel) * peaks.per_second));
      let peak = 0;
      for (let i = Math.max(0, a); i < Math.min(b, peaks.peaks.length); i++) peak = Math.max(peak, peaks.peaks[i]);
      const bar = Math.max(1, (peak / maxPeak) * (height - 4));
      context.fillRect(px, (height - bar) / 2, 1, bar);
    }
  }, [peaks, from, to, width, maxPeak]);

  return <canvas ref={canvasRef} className="waveform" style={{ width }} />;
}
