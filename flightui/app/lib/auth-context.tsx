"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { jwtDecode } from "jwt-decode";
import { api, TokenPair, UserResponse } from "./api";

interface JwtPayload {
  sub: string;
  username: string;
  is_admin: boolean;
  exp: number;
}

interface AuthState {
  accessToken: string | null;
  user: UserResponse | null;
  loading: boolean;
}

interface AuthContextValue extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const REFRESH_KEY = "refresh_token";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    accessToken: null,
    user: null,
    loading: true,
  });

  const applyTokens = useCallback(async (tokens: TokenPair) => {
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
    const user = await api.me(tokens.access_token);
    setState({ accessToken: tokens.access_token, user, loading: false });
  }, []);

  // On mount: try to restore session via stored refresh token
  useEffect(() => {
    const stored = localStorage.getItem(REFRESH_KEY);
    if (!stored) {
      setState((s) => ({ ...s, loading: false }));
      return;
    }
    api
      .refresh(stored)
      .then(applyTokens)
      .catch(() => {
        localStorage.removeItem(REFRESH_KEY);
        setState((s) => ({ ...s, loading: false }));
      });
  }, [applyTokens]);

  // Proactive access-token refresh before expiry
  useEffect(() => {
    if (!state.accessToken) return;
    const { exp } = jwtDecode<JwtPayload>(state.accessToken);
    const msUntilExpiry = exp * 1000 - Date.now() - 30_000; // 30 s margin
    if (msUntilExpiry <= 0) return;
    const timer = setTimeout(async () => {
      const stored = localStorage.getItem(REFRESH_KEY);
      if (!stored) return;
      try {
        await applyTokens(await api.refresh(stored));
      } catch {
        setState({ accessToken: null, user: null, loading: false });
        localStorage.removeItem(REFRESH_KEY);
      }
    }, msUntilExpiry);
    return () => clearTimeout(timer);
  }, [state.accessToken, applyTokens]);

  const login = useCallback(
    async (username: string, password: string) => {
      const tokens = await api.login(username, password);
      await applyTokens(tokens);
    },
    [applyTokens]
  );

  const logout = useCallback(async () => {
    const stored = localStorage.getItem(REFRESH_KEY);
    if (stored) {
      await api.logout(stored).catch(() => {});
      localStorage.removeItem(REFRESH_KEY);
    }
    setState({ accessToken: null, user: null, loading: false });
  }, []);

  const register = useCallback(
    async (username: string, email: string, password: string) => {
      await api.register(username, email, password);
      await login(username, password);
    },
    [login]
  );

  return (
    <AuthContext.Provider value={{ ...state, login, logout, register }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
