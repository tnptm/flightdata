const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserResponse {
  user_id: number;
  username: string;
  email: string;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
}

export interface FlightResponse {
  icao24: string;
  timestamp: string;
  callsign: string | null;
  origin_country: string | null;
  longitude: number | null;
  latitude: number | null;
  baro_altitude: number | null;
  on_ground: boolean | null;
  velocity: number | null;
  true_track: number | null;
  vertical_rate: number | null;
  geo_altitude: number | null;
  squawk: string | null;
  position_source: number | null;
}

export interface PlaneResponse {
  icao24: string;
  manufacturerName: string | null;
  model: string | null;
  typecode: string | null;
  registration: string | null;
  operator: string | null;
  operatorIcao: string | null;
  country: string | null;
  built: number | null;
  engines: number | null;
  categoryDescription: string | null;
  serialNumber: string | null;
  owner: string | null;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail?.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  register(username: string, email: string, password: string) {
    return request<UserResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, email, password }),
    });
  },

  login(username: string, password: string) {
    const body = new URLSearchParams({ username, password });
    return fetch(`${API_BASE}/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    }).then(async (res) => {
      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(detail?.detail ?? res.statusText);
      }
      return res.json() as Promise<TokenPair>;
    });
  },

  logout(refresh_token: string) {
    return fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token }),
    });
  },

  refresh(refresh_token: string) {
    return request<TokenPair>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token }),
    });
  },

  me(access_token: string) {
    return request<UserResponse>("/users/me", {
      headers: { Authorization: `Bearer ${access_token}` },
    });
  },

  flights(
    access_token: string,
    bounds: { minLon: number; minLat: number; maxLon: number; maxLat: number }
  ) {
    const params = new URLSearchParams({
      min_lon: String(bounds.minLon),
      min_lat: String(bounds.minLat),
      max_lon: String(bounds.maxLon),
      max_lat: String(bounds.maxLat),
    });
    return request<FlightResponse[]>(`/flights?${params}`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
  },

  plane(icao24: string, access_token: string) {
    return request<PlaneResponse>(`/planes/${icao24}`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
  },
};
