"use client";

import { useEffect, useRef, useCallback } from "react";
import type { Map as LeafletMap, Marker } from "leaflet";
import type { FlightResponse } from "../lib/api";

interface FlightMapProps {
  flights: FlightResponse[];
  onBoundsChange: (bounds: {
    minLon: number;
    minLat: number;
    maxLon: number;
    maxLat: number;
  }) => void;
}

export default function FlightMap({ flights, onBoundsChange }: FlightMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const markersRef = useRef<Map<string, Marker>>(new Map());

  // Stable callback ref to avoid re-mounting the map on re-render
  const onBoundsChangeRef = useRef(onBoundsChange);
  useEffect(() => {
    onBoundsChangeRef.current = onBoundsChange;
  }, [onBoundsChange]);

  // Mount map once
  useEffect(() => {
    if (!containerRef.current) return;
    let cancelled = false;

    import("leaflet").then((L) => {
      if (cancelled || mapRef.current) return;

      // Fix default icon paths broken by bundlers
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
        iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
        shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
      });

      const map = L.map(containerRef.current!).setView([20, 0], 3);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19,
      }).addTo(map);

      const emitBounds = () => {
        const b = map.getBounds();
        onBoundsChangeRef.current({
          minLon: b.getWest(),
          minLat: b.getSouth(),
          maxLon: b.getEast(),
          maxLat: b.getNorth(),
        });
      };

      map.on("moveend", emitBounds);
      map.on("zoomend", emitBounds);
      mapRef.current = map;

      // Emit initial bounds after tiles settle
      setTimeout(emitBounds, 300);
    });

    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
      markersRef.current.clear();
      // Clear Leaflet's internal container flag so re-mount works cleanly
      if (containerRef.current) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        delete (containerRef.current as any)._leaflet_id;
      }
    };
  }, []);

  // Sync flight markers whenever the flights prop changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    import("leaflet").then((L) => {
      const incoming = new Set(flights.map((f) => f.icao24));
      const planeIcon = (track: number | null) =>
        L.divIcon({
          className: "",
          html: `<div style="transform:rotate(${track ?? 0}deg);font-size:18px;line-height:1;">✈</div>`,
          iconSize: [20, 20],
          iconAnchor: [10, 10],
        });

      // Remove stale markers
      for (const [id, marker] of markersRef.current.entries()) {
        if (!incoming.has(id)) {
          marker.remove();
          markersRef.current.delete(id);
        }
      }

      // Add / update markers
      for (const flight of flights) {
        if (flight.latitude == null || flight.longitude == null) continue;
        const existing = markersRef.current.get(flight.icao24);
        const icon = planeIcon(flight.true_track);
        const popup = [
          `<b>${flight.callsign?.trim() || flight.icao24}</b>`,
          `Country: ${flight.origin_country ?? "—"}`,
          `Alt: ${flight.baro_altitude != null ? flight.baro_altitude.toFixed(0) + " m" : "—"}`,
          `Speed: ${flight.velocity != null ? flight.velocity.toFixed(0) + " m/s" : "—"}`,
          `On ground: ${flight.on_ground ? "Yes" : "No"}`,
          `Updated: ${new Date(flight.timestamp).toLocaleTimeString()}`,
        ].join("<br>");

        if (existing) {
          existing.setLatLng([flight.latitude, flight.longitude]);
          existing.setIcon(icon);
          existing.setPopupContent(popup);
        } else {
          const marker = L.marker([flight.latitude, flight.longitude], { icon })
            .bindPopup(popup)
            .addTo(map);
          markersRef.current.set(flight.icao24, marker);
        }
      }
    });
  }, [flights]);

  return (
    <>
      {/* Leaflet CSS */}
      <link
        rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
        crossOrigin=""
      />
      <div ref={containerRef} className="w-full h-full" />
    </>
  );
}
