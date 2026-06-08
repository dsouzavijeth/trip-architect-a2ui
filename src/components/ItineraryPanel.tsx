"use client";

import { useMemo, useState } from "react";
import { useTripStops, type TripStop } from "@/a2ui/trip-store";

const ACCENT: Record<string, string> = {
  sight: "#E2A03F",
  food: "#D8643A",
  stay: "#7C8B5A",
  nature: "#5C8A6A",
  culture: "#9A6FB0",
  nightlife: "#5E72A8",
};

type Entry = { stop: TripStop; index: number };
type Group = { label: string; entries: Entry[] };

function groupByDay(stops: TripStop[]): Group[] {
  const order: string[] = [];
  const buckets = new Map<string, Entry[]>();
  stops.forEach((stop, index) => {
    const label = stop.time?.split("·")[0].trim() || "Stops";
    if (!buckets.has(label)) {
      buckets.set(label, []);
      order.push(label);
    }
    buckets.get(label)!.push({ stop, index });
  });
  return order.map((label) => ({ label, entries: buckets.get(label)! }));
}

/**
 * Floating, collapsible "Your plan" overlay on the map. Reads the same
 * tripStore the map does, so it always reflects the approved itinerary — the
 * clear, ordered final plan. Numbers match the map pins. Additive: renders
 * nothing until the first stop is approved.
 */
export function ItineraryPanel() {
  const stops = useTripStops();
  const [open, setOpen] = useState(true);
  const groups = useMemo(() => groupByDay(stops), [stops]);

  if (stops.length === 0) return null;

  return (
    <div className="absolute top-3 left-3 z-[1000] w-[268px] max-w-[72%] rounded-xl border border-[var(--line)] bg-[var(--bg)]/92 backdrop-blur-sm shadow-2xl overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3.5 py-2.5 text-left"
      >
        <span className="flex items-baseline gap-2">
          <span className="font-semibold text-[var(--ink)] text-[15px]">
            Your plan
          </span>
          <span className="text-[11px] uppercase tracking-[0.12em] text-[var(--ink)]/55">
            {stops.length} {stops.length === 1 ? "stop" : "stops"}
          </span>
        </span>
        <span
          className="text-[var(--ink)]/55 text-xs transition-transform"
          style={{ transform: open ? "rotate(180deg)" : "none" }}
        >
          ▾
        </span>
      </button>

      {open && (
        <div className="max-h-[min(52vh,420px)] overflow-y-auto px-3.5 pb-3 pt-0.5 space-y-3">
          {groups.map((group) => (
            <div key={group.label}>
              <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--ink)]/45 mb-1.5">
                {group.label}
              </div>
              <ol className="space-y-2">
                {group.entries.map(({ stop, index }) => {
                  const accent = ACCENT[stop.category] ?? ACCENT.sight;
                  return (
                    <li key={stop.id} className="flex gap-2.5">
                      <span
                        className="mt-0.5 flex-none grid place-items-center h-5 w-5 rounded-full text-[11px] font-semibold text-[#1b1916]"
                        style={{ background: accent }}
                      >
                        {index + 1}
                      </span>
                      <div className="min-w-0">
                        <div className="text-[13.5px] font-medium text-[var(--ink)] leading-snug">
                          {stop.name}
                        </div>
                        {stop.note && (
                          <div className="text-[12px] text-[var(--ink)]/60 leading-snug mt-0.5">
                            {stop.note}
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
