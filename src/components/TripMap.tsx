"use client";

import dynamic from "next/dynamic";

// Leaflet touches `window` at import time, so load the map client-only.
export const TripMap = dynamic(() => import("./TripMapInner"), {
  ssr: false,
  loading: () => <div style={{ width: "100%", height: "100%", background: "#15140f" }} />,
});
