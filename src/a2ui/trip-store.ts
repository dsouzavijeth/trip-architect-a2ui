"use client";

import { useSyncExternalStore } from "react";

export type TripStop = {
  id: string;
  name: string;
  lat: number;
  lng: number;
  category: string;
  note: string;
  time?: string;
};

let stops: TripStop[] = [];
const listeners = new Set<() => void>();

function emit() {
  for (const fn of listeners) fn();
}

export const tripStore = {
  addStop(s: TripStop) {
    if (!s || s.lat == null || s.lng == null) return;
    if (stops.some((p) => p.name.toLowerCase() === String(s.name).toLowerCase()))
      return;
    stops = [...stops, s];
    emit();
  },
  clear() {
    stops = [];
    emit();
  },
  get(): TripStop[] {
    return stops;
  },
  subscribe(fn: () => void) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
};

/** React hook: the current approved itinerary, in order. */
export function useTripStops(): TripStop[] {
  return useSyncExternalStore(
    tripStore.subscribe,
    tripStore.get,
    () => stops,
  );
}
