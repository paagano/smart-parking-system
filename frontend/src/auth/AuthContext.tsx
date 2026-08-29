import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { authApi, usersApi, type CurrentUser } from "../api";

// ==========================================================
// Types
// ==========================================================

interface AuthContextValue {
  user: CurrentUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;

  login: (email: string, password: string) => Promise<CurrentUser>;

  logout: () => void;
}

// ==========================================================
// Context
// ==========================================================

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

// ==========================================================
// Provider
// ==========================================================

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);

  const [isLoading, setIsLoading] = useState(true);

  // ========================================================
  // Restore Session
  // ========================================================

  useEffect(() => {
    const restoreSession = async () => {
      console.log("[SmartPark Auth] Checking for existing token...");

      const token = localStorage.getItem("smartpark_token");

      if (!token) {
        console.log("[SmartPark Auth] No token found.");

        setUser(null);
        setIsLoading(false);

        return;
      }

      console.log("[SmartPark Auth] Token found. Calling /users/me...");

      try {
        const currentUser = await usersApi.me();

        console.log("[SmartPark Auth] Session restored:", currentUser);

        setUser(currentUser);
      } catch (error) {
        console.error("[SmartPark Auth] Session restoration failed:", error);

        localStorage.removeItem("smartpark_token");

        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };

    void restoreSession();
  }, []);

  // ========================================================
  // Login
  // ========================================================

  const login = async (
    email: string,
    password: string,
  ): Promise<CurrentUser> => {
    console.log("[SmartPark Auth] Starting login...", {
      email,
    });

    try {
      // ----------------------------------------------------
      // STEP 1
      // ----------------------------------------------------

      console.log("[SmartPark Auth] STEP 1: POST /auth/login");

      const tokenResponse = await authApi.login(email, password);

      console.log(
        "[SmartPark Auth] STEP 1 SUCCESS: Login response received.",
        tokenResponse,
      );

      // ----------------------------------------------------
      // Validate token
      // ----------------------------------------------------

      if (!tokenResponse || !tokenResponse.access_token) {
        console.error(
          "[SmartPark Auth] Login response does not contain access_token.",
          tokenResponse,
        );

        throw new Error(
          "Authentication succeeded but no access token was returned.",
        );
      }

      console.log("[SmartPark Auth] Access token received.");

      // ----------------------------------------------------
      // STEP 2
      // ----------------------------------------------------

      localStorage.setItem("smartpark_token", tokenResponse.access_token);

      console.log(
        "[SmartPark Auth] STEP 2 SUCCESS: JWT stored in localStorage.",
      );

      // ----------------------------------------------------
      // STEP 3
      // ----------------------------------------------------

      console.log("[SmartPark Auth] STEP 3: Calling GET /users/me");

      const currentUser = await usersApi.me();

      console.log(
        "[SmartPark Auth] STEP 3 SUCCESS: Current user received.",
        currentUser,
      );

      // ----------------------------------------------------
      // STEP 4
      // ----------------------------------------------------

      setUser(currentUser);

      console.log("[SmartPark Auth] STEP 4 SUCCESS: User authenticated.");

      return currentUser;
    } catch (error) {
      console.error("[SmartPark Auth] LOGIN FAILED:", error);

      localStorage.removeItem("smartpark_token");

      setUser(null);

      throw error;
    }
  };

  // ========================================================
  // Logout
  // ========================================================

  const logout = () => {
    console.log("[SmartPark Auth] Logging out...");

    authApi.logout();

    setUser(null);
  };

  // ========================================================
  // Provider
  // ========================================================

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: user !== null,
        isLoading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ==========================================================
// Hook
// ==========================================================

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }

  return context;
}
