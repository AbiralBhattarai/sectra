import { useEffect } from "react";
import { layout, mediaTime, outputTime, placedAt, type Placed } from "../sequence";
import { useEditor } from "../store";
import type { BrollItem } from "../types";
import { setGain } from "./audio";
import { brollVideos, slotCanvases, slotRightRects, slotVideos } from "./elements";
import { segmentGain, slotTargets } from "./playback";

/** The preview's clock: during video playback, the active video element's presentation
 * time drives output time (hardware clock). Monotonic clock progression and hysteresis
 * segment handoff prevent midpoint oscillations during transitions and cold-start stalls at cuts. */
export function usePlaybackEngine(): void {
  useEffect(() => {
    let handle = 0;
    let last = performance.now();
    let currentPrimaryIndex: number | null = null;
    let lastPlayhead = -1;
    const startingSlots = new Set<number>();
    const startingBroll = new Set<string>();

    const tick = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      const state = useEditor.getState();
      if (state.edl) {
        const placed = layout(state.edl.segments);
        const duration = placed.length ? placed[placed.length - 1].end : 0;
        let t = state.playhead;

        // Maintain hysteresis on the primary segment during active playback.
        // This prevents high-frequency oscillations between slots around transition midpoints and cut points.
        let primary: Placed | null = null;
        if (state.playing) {
          // Detect user scrubbing or jumping while playing
          const scrubbed =
            lastPlayhead >= 0 && (t < lastPlayhead - 0.05 || t > lastPlayhead + 0.3);

          if (currentPrimaryIndex === null || scrubbed) {
            primary = placedAt(placed, t);
            currentPrimaryIndex = primary?.index ?? null;
          } else {
            // Continuous forward playback: advance primary only when crossing ownership boundary
            while (
              currentPrimaryIndex < placed.length - 1 &&
              t >= placed[currentPrimaryIndex].ownEnd
            ) {
              currentPrimaryIndex++;
            }
            primary = placed[currentPrimaryIndex] ?? null;
          }

          if (primary && primary.segment.kind === "video") {
            const slot = primary.index % 2;
            const element = slotVideos[slot];
            if (element) {
              const rawVideoT = outputTime(primary, element.currentTime);
              // Video presentation time clamped so it cannot regress before ownStart
              const videoT = Math.min(Math.max(rawVideoT, primary.ownStart), duration);

              // If the user scrubbed/jumped playhead away from current video presentation:
              if (Math.abs(videoT - t) > 0.5) {
                const desired = mediaTime(primary, t);
                if (!element.seeking && Math.abs(element.currentTime - desired) > 0.03) {
                  element.currentTime = desired;
                }
              } else if (!element.seeking && element.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
                // Strict monotonic clock advancement: timeline time never regresses backwards
                t = Math.min(Math.max(t, videoT), duration);
              }
            }
          } else {
            // Freeze frames, images, or gaps advance via wall clock
            t = Math.min(t + dt, duration);
          }

          if (t >= duration) {
            state.setPlaying(false);
            t = duration;
            currentPrimaryIndex = null;
          }
          state.setPlayhead(t);
        } else {
          // Paused: primary directly follows playhead position
          primary = placedAt(placed, t);
          currentPrimaryIndex = primary?.index ?? null;
        }

        lastPlayhead = t;

        const targets = slotTargets(placed, t);
        const playing = state.playing && t < duration;
        targets.forEach((target, slot) => {
          const p = target?.placed ?? null;
          const isPrimary = !!p && !!primary && p.index === primary.index;
          syncSlot(slot, p, !!target?.active, isPrimary, t, playing, duration, startingSlots);
        });
        for (const item of state.edl.broll) syncBroll(item, t, playing, startingBroll);
        drawSplitPanes();
      }
      handle = requestAnimationFrame(tick);
    };
    handle = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(handle);
      for (const video of slotVideos) video?.pause();
      for (const video of brollVideos.values()) video.pause();
      startingSlots.clear();
      startingBroll.clear();
    };
  }, []);
}

function syncSlot(
  slot: number,
  p: Placed | null,
  active: boolean,
  isPrimary: boolean,
  t: number,
  playing: boolean,
  duration: number,
  startingSlots: Set<number>,
) {
  const element = slotVideos[slot];
  if (!element) return;
  const segment = p?.segment;
  if (!p || !segment || segment.kind === "image") {
    if (!element.paused) element.pause();
    return;
  }
  const desired = active ? mediaTime(p, t) : segment.kind === "video" ? segment.start : segment.at;

  if (playing && active && segment.kind === "video") {
    if (element.paused) {
      if (element.seeking) return;
      if (Math.abs(element.currentTime - desired) > 0.03) {
        element.currentTime = desired;
        element.addEventListener(
          "seeked",
          () => {
            if (useEditor.getState().playing) {
              void element.play().catch(() => undefined);
            }
          },
          { once: true },
        );
        return;
      }
      if (!startingSlots.has(slot)) {
        startingSlots.add(slot);
        element
          .play()
          .catch(() => undefined)
          .finally(() => {
            startingSlots.delete(slot);
          });
      }
    } else if (!isPrimary) {
      // Secondary active video (e.g. incoming segment during a transition):
      // Smoothly nudge playbackRate to stay aligned without hard seeking.
      const drift = element.currentTime - desired;
      const targetRate =
        Math.abs(drift) > 0.05 && Math.abs(drift) < 0.5
          ? segment.speed * (drift > 0 ? 0.95 : 1.05)
          : segment.speed;
      if (element.playbackRate !== targetRate) {
        element.playbackRate = targetRate;
      }
      if (Math.abs(drift) >= 0.5 && !element.seeking) {
        element.currentTime = desired;
      }
    } else {
      if (element.playbackRate !== segment.speed) {
        element.playbackRate = segment.speed;
      }
    }
    // Note: If isPrimary and playing, the video element is driving timeline time.
    // We never overwrite element.currentTime during playback to prevent seek stutter.
  } else {
    if (!element.paused) element.pause();
    if (!element.seeking && Math.abs(element.currentTime - desired) > 0.03) {
      element.currentTime = desired;
    }
  }

  const edl = useEditor.getState().edl!;
  setGain(element, active ? segmentGain(edl, p, t, duration) : 0);
}

function syncBroll(
  item: BrollItem,
  t: number,
  playing: boolean,
  startingBroll: Set<string>,
) {
  const element = brollVideos.get(item.id);
  if (!element) return;
  const inside = t >= item.start && t < item.start + item.duration;
  const desired = item.media_start + Math.max(0, t - item.start);
  if (playing && inside) {
    if (element.paused) {
      if (element.seeking) return;
      if (Math.abs(element.currentTime - desired) > 0.05) {
        element.currentTime = desired;
        element.addEventListener(
          "seeked",
          () => {
            if (useEditor.getState().playing) {
              void element.play().catch(() => undefined);
            }
          },
          { once: true },
        );
        return;
      }
      if (!startingBroll.has(item.id)) {
        startingBroll.add(item.id);
        element
          .play()
          .catch(() => undefined)
          .finally(() => {
            startingBroll.delete(item.id);
          });
      }
    } else {
      const drift = element.currentTime - desired;
      const targetRate =
        Math.abs(drift) > 0.05 && Math.abs(drift) < 0.5
          ? drift > 0 ? 0.95 : 1.05
          : 1;
      if (element.playbackRate !== targetRate) {
        element.playbackRate = targetRate;
      }
      if (Math.abs(drift) >= 0.5 && !element.seeking) {
        element.currentTime = desired;
      }
    }
  } else {
    if (!element.paused) element.pause();
    if (!element.seeking && Math.abs(element.currentTime - desired) > 0.03) {
      element.currentTime = desired;
    }
  }
  setGain(element, inside ? item.volume : 0);
}

/** Split screen: each slot's bottom pane is a canvas copying the right half of the same
 * video element every frame — a second <video> would drift. */
function drawSplitPanes() {
  slotCanvases.forEach((canvas, slot) => {
    const video = slotVideos[slot];
    const rect = slotRightRects[slot];
    if (!canvas || !video || !rect || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
    canvas.getContext("2d")!.drawImage(video, rect.x, rect.y, rect.width, rect.height, 0, 0, canvas.width, canvas.height);
  });
}
