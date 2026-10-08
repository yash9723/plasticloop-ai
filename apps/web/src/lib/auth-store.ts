import { create } from "zustand";

export type Role =
  | "super_admin"
  | "gp_admin"
  | "collector"
  | "driver"
  | "mrf_operator"
  | "processor"
  | "household"
  | "evaluator";

export interface Membership {
  organization_id: string;
  organization_name: string | null;
  organization_type: string | null;
  role: Role;
  village_id: string | null;
  facility_id: string | null;
}

export interface Me {
  id: string;
  email: string;
  phone: string | null;
  full_name: string;
  preferred_language: string;
  roles: Role[];
  memberships: Membership[];
  household_id: string | null;
  village_ids: string[];
  facility_ids: string[];
  read_only: boolean;
  demo_mode: boolean;
}

type Status = "unknown" | "authenticated" | "anonymous" | "offline";

interface AuthState {
  accessToken: string | null;
  user: Me | null;
  status: Status;
  setSession: (token: string, user: Me) => void;
  setUser: (user: Me) => void;
  setOffline: (user: Me) => void;
  clear: () => void;
}

const PROFILE_KEY = "pl_profile";

/** Only non-sensitive fields are cached (for offline collector mode). Tokens are never persisted in JS storage. */
function cacheProfile(user: Me) {
  try {
    const { id, full_name, roles, village_ids, facility_ids, preferred_language, demo_mode, read_only } = user;
    localStorage.setItem(
      PROFILE_KEY,
      JSON.stringify({ id, full_name, roles, village_ids, facility_ids, preferred_language, demo_mode, read_only }),
    );
  } catch {
    /* storage unavailable */
  }
}

export function loadCachedProfile(): Me | null {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw);
    return { email: "", phone: null, memberships: [], household_id: null, ...p } as Me;
  } catch {
    return null;
  }
}

export function forgetCachedProfile() {
  try {
    localStorage.removeItem(PROFILE_KEY);
  } catch {
    /* ignore */
  }
}

export const useAuth = create<AuthState>()((set) => ({
  accessToken: null,
  user: null,
  status: "unknown",
  setSession: (accessToken, user) => {
    cacheProfile(user);
    set({ accessToken, user, status: "authenticated" });
  },
  setUser: (user) => {
    cacheProfile(user);
    set({ user });
  },
  setOffline: (user) => set({ user, status: "offline", accessToken: null }),
  clear: () => set({ accessToken: null, user: null, status: "anonymous" }),
}));

export function hasRole(user: Pick<Me, "roles"> | null | undefined, ...roles: Role[]): boolean {
  if (!user) return false;
  return user.roles.includes("super_admin") || user.roles.some((r) => roles.includes(r));
}

/** Landing route after sign-in: field staff go straight to the collector app. */
export function homeFor(user: Pick<Me, "roles">): string {
  if (user.roles.some((r) => r === "collector" || r === "driver") && !user.roles.includes("gp_admin")) return "/collector";
  return "/dashboard";
}

/** Evaluators (without other roles) may look at everything but change nothing. */
export function isReadOnly(user: Pick<Me, "roles" | "read_only"> | null | undefined): boolean {
  return !!user && (user.read_only || (user.roles.length === 1 && user.roles[0] === "evaluator"));
}
