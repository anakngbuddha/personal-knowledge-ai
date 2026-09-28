import React, { useEffect, useMemo, useState } from "react";
import "./SeaBubbles.css";

export interface SeaBubblesProps {
  count?: number;
  variant?: "landing" | "dashboard" | "minimal";
  interactive?: boolean;
  className?: string;
}

interface BubbleConfig {
  id: number;
  leftPercent: number;
  size: number;
  duration: number;
  delay: number;
  depth: "deep" | "mid" | "crisp";
  targetOpacity: number;
  reducedTop: number;
}

export function SeaBubbles({
  count = 20,
  variant = "landing",
  interactive = false,
  className = "",
}: SeaBubblesProps) {
  // Track popped bubbles for interactive delight
  const [poppedIds, setPoppedIds] = useState<Set<number>>(new Set());
  const [paused, setPaused] = useState(() => typeof document !== "undefined" && document.hidden);
  useEffect(() => {
    const onVisibilityChange = () => setPaused(document.hidden);
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  }, []);

  // Generate deterministic-looking bubbles distributed across the viewport
  const bubbles = useMemo<BubbleConfig[]>(() => {
    const list: BubbleConfig[] = [];
    const seedPrng = (seed: number) => {
      const x = Math.sin(seed) * 10000;
      return x - Math.floor(x);
    };

    for (let i = 0; i < count; i++) {
      const r1 = seedPrng(i * 13 + 7);
      const r2 = seedPrng(i * 29 + 17);
      const r3 = seedPrng(i * 43 + 31);
      const r4 = seedPrng(i * 71 + 5);

      // Distribute evenly across horizontal width with slight jitter
      const baseCol = (i / count) * 94 + 3; // 3% to 97%
      const jitter = (r1 - 0.5) * (80 / count);
      const leftPercent = Math.max(2, Math.min(98, baseCol + jitter));

      // Size distribution: mostly small/medium, occasional deep macro-bubble
      let size = 6 + r2 * 14; // 6px to 20px
      let depth: "deep" | "mid" | "crisp" = "mid";
      let targetOpacity = 0.5 + r4 * 0.25;

      if (r2 < 0.25) {
        // Deep background macro bubble
        size = 22 + r3 * 16; // 22px to 38px
        depth = "deep";
        targetOpacity = 0.25;
      } else if (r2 > 0.75) {
        // Small crisp micro-bubble
        size = 4 + r3 * 4; // 4px to 8px
        depth = "crisp";
        targetOpacity = 0.8;
      }

      // Physics durations: larger bubbles rise slightly slower or float with more poise
      const duration = depth === "deep" ? 18 + r3 * 10 : 9 + r3 * 8; // 9s to 28s
      const delay = r4 * 14; // staggered start
      const reducedTop = 15 + r2 * 70; // 15% to 85% for reduced motion static position

      list.push({
        id: i,
        leftPercent,
        size,
        duration,
        delay,
        depth,
        targetOpacity,
        reducedTop,
      });
    }

    return list;
  }, [count]);

  const handlePop = (id: number) => {
    if (!interactive) return;
    setPoppedIds((prev) => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
    // Respawn bubble after 4 seconds
    setTimeout(() => {
      setPoppedIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }, 4000);
  };

  return (
    <div
      className={`sea-bubbles-container sea-bubbles--${variant} ${className}`}
      aria-hidden="true"
      data-paused={paused}
    >
      {bubbles.map((b) => {
        if (poppedIds.has(b.id)) return null;

        return (
          <div
            key={b.id}
            className="sea-bubble-wrapper"
            style={
              {
                left: `${b.leftPercent}%`,
                animation: `seaBubbleAscent ${b.duration}s linear infinite`,
                animationDelay: `-${b.delay}s`,
                "--bubble-target-opacity": b.targetOpacity,
                "--reduced-top": `${b.reducedTop}%`,
              } as React.CSSProperties
            }
          >
            <div
              className={`sea-bubble sea-bubble--${b.depth} ${interactive ? "sea-bubble-interactive" : ""}`}
              onClick={() => handlePop(b.id)}
              style={
                {
                  width: `${b.size}px`,
                  height: `${b.size}px`,
                  animation: `seaBubbleWobble ${2.5 + (b.id % 3) * 0.7}s ease-in-out infinite`,
                } as React.CSSProperties
              }
              title={interactive ? "Pop bubble" : undefined}
            />
          </div>
        );
      })}
    </div>
  );
}

export default SeaBubbles;
