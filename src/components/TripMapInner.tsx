"use client";

import { useEffect } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Polyline,
  Tooltip,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useTripStops, type TripStop } from "@/a2ui/trip-store";

const ACCENT: Record<string, string> = {
  sight: "#E2A03F",
  food: "#D8643A",
  stay: "#7C8B5A",
  nature: "#5C8A6A",
  culture: "#9A6FB0",
  nightlife: "#5E72A8",
};

const CATEGORY_LABEL: Record<string, string> = {
  sight: "Sight",
  food: "Food",
  stay: "Stay",
  nature: "Nature",
  culture: "Culture",
  nightlife: "Nightlife",
};

// Dark styling for the hover tooltips (Leaflet tooltips default to white).
const TOOLTIP_CSS = `
.leaflet-tooltip.trip-tip {
  background: #1b1916;
  color: #f3ecdf;
  border: 1px solid rgba(243, 236, 223, 0.14);
  border-radius: 10px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.45);
  padding: 0;
  max-width: 240px;
  white-space: normal;
  font-family: system-ui, sans-serif;
}
.leaflet-tooltip.trip-tip::before { display: none; }   /* hide the arrow */
.trip-tip__inner { padding: 9px 12px; }
.trip-tip__cat { font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; font-weight: 600; }
.trip-tip__name { font-size: 14px; font-weight: 600; margin-top: 1px; }
.trip-tip__time { font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase; opacity: 0.6; margin-top: 3px; }
.trip-tip__note { font-size: 12px; line-height: 1.4; opacity: 0.85; margin-top: 5px; }
`;

function pinIcon(index: number, accent: string) {
  return L.divIcon({
    className: "trip-pin-wrap",
    html: `<div style="
      width:28px;height:28px;border-radius:50% 50% 50% 2px;transform:rotate(45deg);
      background:${accent};color:#1b1916;display:grid;place-items:center;
      box-shadow:0 6px 14px rgba(0,0,0,.45);border:1.5px solid rgba(251,246,236,.9);
      font:600 12px/1 system-ui">
        <span style="transform:rotate(-45deg)">${index + 1}</span>
    </div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

function FitToStops({ stops }: { stops: TripStop[] }) {
  const map = useMap();
  useEffect(() => {
    if (stops.length === 0) return;
    if (stops.length === 1) {
      map.flyTo([stops[0].lat, stops[0].lng], 13, { duration: 0.8 });
      return;
    }
    const bounds = L.latLngBounds(stops.map((s) => [s.lat, s.lng]));
    map.flyToBounds(bounds.pad(0.25), { duration: 0.9 });
  }, [stops, map]);
  return null;
}

export default function TripMapInner() {
  const stops = useTripStops();
  const center: [number, number] = stops.length
    ? [stops[0].lat, stops[0].lng]
    : [41.3874, 2.1686];

  return (
    <>
      <style>{TOOLTIP_CSS}</style>
      <MapContainer
        center={center}
        zoom={12}
        zoomControl={false}
        attributionControl={false}
        style={{ width: "100%", height: "100%", background: "#15140f" }}
      >
        <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
        <FitToStops stops={stops} />
        {stops.length > 1 && (
          <Polyline
            positions={stops.map((s) => [s.lat, s.lng])}
            pathOptions={{
              color: "#E2A03F",
              weight: 2,
              opacity: 0.7,
              dashArray: "1 8",
            }}
          />
        )}
        {stops.map((s, i) => {
          const accent = ACCENT[s.category] ?? ACCENT.sight;
          return (
            <Marker key={s.id} position={[s.lat, s.lng]} icon={pinIcon(i, accent)}>
              {/* Hover for details. */}
              <Tooltip
                direction="top"
                offset={[0, -16]}
                opacity={1}
                className="trip-tip"
              >
                <div className="trip-tip__inner">
                  <div className="trip-tip__cat" style={{ color: accent }}>
                    {CATEGORY_LABEL[s.category] ?? s.category}
                  </div>
                  <div className="trip-tip__name">
                    {i + 1}. {s.name}
                  </div>
                  {s.time && <div className="trip-tip__time">{s.time}</div>}
                  {s.note && <div className="trip-tip__note">{s.note}</div>}
                </div>
              </Tooltip>
            </Marker>
          );
        })}
      </MapContainer>
    </>
  );
}
