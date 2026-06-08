"use client";

import { useEffect } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Polyline,
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
      {stops.map((s, i) => (
        <Marker
          key={s.id}
          position={[s.lat, s.lng]}
          icon={pinIcon(i, ACCENT[s.category] ?? ACCENT.sight)}
        />
      ))}
    </MapContainer>
  );
}
