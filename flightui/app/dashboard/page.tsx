"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { useAuth } from "../lib/auth-context";
import { api, FlightResponse } from "../lib/api";

// FlightMap uses Leaflet (browser-only) — disable SSR
const FlightMap = dynamic(() => import("../components/FlightMap"), { ssr: false });

const POLL_INTERVAL_MS = 15_000;

export default function DashboardPage() {
  const { user, accessToken, logout, loading } = useAuth();
  const router = useRouter();

  const [flights, setFlights] = useState<FlightResponse[]>([]);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const boundsRef = useRef<{
    minLon: number;
    minLat: number;
    maxLon: number;
    maxLat: number;
  } | null>(null);

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!loading && !accessToken) router.replace("/login");
  }, [loading, accessToken, router]);

  const fetchFlights = useCallback(async () => {
    if (!accessToken || !boundsRef.current) return;
    try {
      const data = await api.flights(accessToken, boundsRef.current);
      setFlights(data);
      setLastUpdated(new Date());
      setFetchError(null);
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : "Failed to fetch flights");
    }
  }, [accessToken]);

  // Fetch when bounds change (set by map move/zoom)
  const handleBoundsChange = useCallback(
    (bounds: { minLon: number; minLat: number; maxLon: number; maxLat: number }) => {
      boundsRef.current = bounds;
      fetchFlights();
    },
    [fetchFlights]
  );

  // Poll on interval
  useEffect(() => {
    const id = setInterval(fetchFlights, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchFlights]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-500">
        Loading…
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-gray-100">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-3 bg-white shadow-sm z-10">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold text-blue-700">✈ FlightData</span>
          <span className="text-sm text-gray-500">
            {flights.length} aircraft in view
          </span>
          {lastUpdated && (
            <span className="text-xs text-gray-400">
              Last update: {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          {fetchError && (
            <span className="text-xs text-red-500">{fetchError}</span>
          )}
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-700">{user?.username}</span>
          <button
            onClick={async () => {
              await logout();
              router.replace("/login");
            }}
            className="text-sm text-red-600 hover:underline"
          >
            Sign out
          </button>
        </div>
      </header>

      {/* Map fills remaining height */}
      <main className="flex-1 relative">
        <FlightMap flights={flights} onBoundsChange={handleBoundsChange} />
      </main>
    </div>
  );
}
