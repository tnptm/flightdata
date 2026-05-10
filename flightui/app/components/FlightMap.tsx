"use client";

import { useEffect, useRef, useCallback } from "react";
import type { Map as LeafletMap, Marker } from "leaflet";
import type { FlightResponse, PlaneResponse, RouteFlight } from "../lib/api";
import { api } from "../lib/api";

interface FlightMapProps {
  flights: FlightResponse[];
  accessToken: string | null;
  onBoundsChange: (bounds: {
    minLon: number;
    minLat: number;
    maxLon: number;
    maxLat: number;
  }) => void;
}

export default function FlightMap({ flights, accessToken, onBoundsChange }: FlightMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const markersRef = useRef<Map<string, Marker>>(new Map());
  const planeCacheRef = useRef<Map<string, PlaneResponse | null>>(new Map());
  const routeCacheRef = useRef<Map<string, RouteFlight[] | null>>(new Map());
  const accessTokenRef = useRef(accessToken);
  useEffect(() => { accessTokenRef.current = accessToken; }, [accessToken]);

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
          html: `<div style="transform:rotate(${(track ?? 0) - 90}deg);font-size:18px;line-height:1;color:#1e3a8a;">✈</div>`,
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

        const metersToFt = (m: number) => Math.round(m * 3.28084).toLocaleString();
        const baroM = flight.baro_altitude;
        const altStr = baroM != null
          ? `${baroM.toFixed(0)} m / ${metersToFt(baroM)} ft`
          : "—";
        const speedKmh = flight.velocity != null
          ? ` (${(flight.velocity * 3.6).toFixed(0)} km/h)`
          : "";
        const speedStr = flight.velocity != null
          ? `${flight.velocity.toFixed(0)} m/s${speedKmh}`
          : "—";
        const headingStr = flight.true_track != null
          ? `${flight.true_track.toFixed(1)}°`
          : "—";

        const basePopup = (planeData?: PlaneResponse | null, routeData?: RouteFlight[] | null) => {
          const lines = [
            `<b>${flight.callsign?.trim() || flight.icao24}</b> <span style="color:#888;font-size:0.85em">(${flight.icao24.toUpperCase()})</span>`,
            `<b>Country:</b> ${flight.origin_country ?? "—"}`,
            `<b>Altitude:</b> ${altStr}`,
            `<b>Speed:</b> ${speedStr}`,
            `<b>Heading:</b> ${headingStr}`,
            `<b>On ground:</b> ${flight.on_ground ? "Yes" : "No"}`,
            `<b>Updated:</b> ${new Date(flight.timestamp).toLocaleTimeString()}`,
          ];

          if (planeData === undefined) {
            lines.push(`<hr style="margin:4px 0"><i style="color:#888">Loading aircraft data…</i>`);
          } else if (planeData === null) {
            // no data available — omit section
          } else {
            lines.push(`<hr style="margin:4px 0"><b>Aircraft</b>`);
            if (planeData.manufacturerName) lines.push(`<b>Manufacturer:</b> ${planeData.manufacturerName}`);
            if (planeData.model) lines.push(`<b>Model:</b> ${planeData.model}`);
            if (planeData.typecode) lines.push(`<b>Type:</b> ${planeData.typecode}`);
            if (planeData.registration) lines.push(`<b>Registration:</b> ${planeData.registration}`);
            if (planeData.operator) lines.push(`<b>Operator:</b> ${planeData.operator}`);
            if (planeData.owner) lines.push(`<b>Owner:</b> ${planeData.owner}`);
            if (planeData.built) lines.push(`<b>Built:</b> ${planeData.built}`);
            if (planeData.engines) lines.push(`<b>Engines:</b> ${planeData.engines}`);
            if (planeData.categoryDescription) lines.push(`<b>Category:</b> ${planeData.categoryDescription}`);
          }

          if (routeData === undefined) {
            lines.push(`<hr style="margin:4px 0"><i style="color:#888">Loading route…</i>`);
          } else if (routeData && routeData.length > 0) {
            lines.push(`<hr style="margin:4px 0"><b>Route Info</b>`);
            for (const f of routeData.slice(0, 3)) {
              if (f.is_live) {
                const since = f.first_seen
                  ? new Date(f.first_seen).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
                  : "?";
                lines.push(`✈ Live track · airborne since ${since} UTC`);
              } else {
                const dep = f.departure_airport ?? "?";
                const arr = f.arrival_airport ?? "?";
                const date = f.first_seen
                  ? new Date(f.first_seen).toLocaleDateString(undefined, { month: "short", day: "numeric" })
                  : "";
                lines.push(`${dep} → ${arr}${date ? ` <span style="color:#888;font-size:0.85em">(${date})</span>` : ""}`);
              }
            }
          }

          return lines.join("<br>");
        };

        const onPopupOpen = () => {
          const marker = markersRef.current.get(flight.icao24);
          if (!marker || !accessTokenRef.current) return;

          const planeHit = planeCacheRef.current.has(flight.icao24);
          const routeHit = routeCacheRef.current.has(flight.icao24);

          // Both cached — render immediately
          if (planeHit && routeHit) {
            marker.setPopupContent(basePopup(
              planeCacheRef.current.get(flight.icao24),
              routeCacheRef.current.get(flight.icao24),
            ));
            return;
          }

          // Show partial/loading state while fetching
          marker.setPopupContent(basePopup(
            planeHit ? planeCacheRef.current.get(flight.icao24) : undefined,
            routeHit ? routeCacheRef.current.get(flight.icao24) : undefined,
          ));

          const token = accessTokenRef.current;
          const planeFetch = planeHit
            ? Promise.resolve(planeCacheRef.current.get(flight.icao24) as PlaneResponse | null)
            : api.plane(flight.icao24, token).catch(() => null as PlaneResponse | null);
          const routeFetch = routeHit
            ? Promise.resolve(routeCacheRef.current.get(flight.icao24) as RouteFlight[] | null)
            : api.route(flight.icao24, token).catch(() => null as RouteFlight[] | null);

          Promise.all([planeFetch, routeFetch]).then(([planeData, routeData]) => {
            if (!planeHit) planeCacheRef.current.set(flight.icao24, planeData);
            if (!routeHit) routeCacheRef.current.set(flight.icao24, routeData);
            if (markersRef.current.has(flight.icao24)) {
              marker.setPopupContent(basePopup(
                planeCacheRef.current.get(flight.icao24),
                routeCacheRef.current.get(flight.icao24),
              ));
            }
          });
        };

        if (existing) {
          existing.setLatLng([flight.latitude, flight.longitude]);
          existing.setIcon(icon);
          existing.setPopupContent(basePopup(
            planeCacheRef.current.get(flight.icao24) ?? null,
            routeCacheRef.current.get(flight.icao24) ?? null,
          ));
          existing.off("popupopen");  // prevent handler accumulation without touching click
          existing.on("popupopen", onPopupOpen);
        } else {
          const marker = L.marker([flight.latitude, flight.longitude], { icon })
            .bindPopup(basePopup(null, null))
            .on("popupopen", onPopupOpen)
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
