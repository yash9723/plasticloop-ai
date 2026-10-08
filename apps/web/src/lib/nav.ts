import {
  Activity,
  BarChart3,
  Bell,
  Boxes,
  Building2,
  ClipboardList,
  Cpu,
  Factory,
  FileText,
  FlaskConical,
  Gauge,
  HandCoins,
  HelpCircle,
  History,
  Home,
  IndianRupee,
  LayoutDashboard,
  type LucideIcon,
  MapPin,
  MessageSquareWarning,
  PackageCheck,
  PlayCircle,
  Recycle,
  Route,
  ScanLine,
  Settings,
  ShieldCheck,
  Smartphone,
  Store,
  Truck,
  Users,
  Waypoints,
} from "lucide-react";
import type { Role } from "@/lib/auth-store";

export interface NavItem {
  href: string;
  key: string; // i18n key under nav.items
  icon: LucideIcon;
  roles: Role[] | "all";
}

export interface NavSection {
  key: string; // i18n key under nav.sections
  items: NavItem[];
}

const STAFF: Role[] = ["gp_admin", "collector", "driver", "mrf_operator", "evaluator"];
const ADMINS: Role[] = ["gp_admin", "evaluator"];
const MRF: Role[] = ["mrf_operator", "evaluator"];

export const NAV: NavSection[] = [
  {
    key: "overview",
    items: [
      { href: "/dashboard", key: "dashboard", icon: LayoutDashboard, roles: "all" },
      { href: "/demo", key: "demo", icon: PlayCircle, roles: ["evaluator", "gp_admin", "mrf_operator"] },
    ],
  },
  {
    key: "field",
    items: [
      { href: "/collector", key: "collector", icon: Smartphone, roles: ["collector", "gp_admin", "driver"] },
      { href: "/collector/offline-queue", key: "offlineQueue", icon: History, roles: ["collector", "gp_admin", "driver"] },
      { href: "/collection-points", key: "collectionPoints", icon: MapPin, roles: [...STAFF, "household"] },
      { href: "/households", key: "households", icon: Home, roles: ["gp_admin", "collector", "evaluator", "household"] },
      { href: "/collections", key: "collections", icon: ClipboardList, roles: [...STAFF, "household"] },
      { href: "/pickup-requests", key: "pickupRequests", icon: HandCoins, roles: ["gp_admin", "collector", "household", "evaluator"] },
    ],
  },
  {
    key: "logistics",
    items: [
      { href: "/routes", key: "routes", icon: Route, roles: ["gp_admin", "driver", "evaluator"] },
      { href: "/routes/planner", key: "routePlanner", icon: Waypoints, roles: ADMINS },
      { href: "/vehicles", key: "vehicles", icon: Truck, roles: ["gp_admin", "driver", "evaluator"] },
    ],
  },
  {
    key: "iot",
    items: [
      { href: "/devices", key: "devices", icon: Cpu, roles: ["gp_admin", "mrf_operator", "evaluator"] },
      { href: "/devices/simulator", key: "simulator", icon: Activity, roles: ["gp_admin", "evaluator"] },
    ],
  },
  {
    key: "mrf",
    items: [
      { href: "/facilities", key: "facilities", icon: Factory, roles: [...MRF, "gp_admin"] },
      { href: "/facilities/intake", key: "intake", icon: PackageCheck, roles: MRF },
      { href: "/inventory", key: "inventory", icon: Boxes, roles: [...MRF, "gp_admin"] },
      { href: "/waste-classification", key: "classification", icon: ScanLine, roles: MRF },
      { href: "/waste-classification/review", key: "classificationReview", icon: FlaskConical, roles: MRF },
    ],
  },
  {
    key: "recovery",
    items: [
      { href: "/processors", key: "processors", icon: Building2, roles: [...MRF, "processor", "gp_admin"] },
      { href: "/processing-transfers", key: "transfers", icon: Truck, roles: [...MRF, "processor"] },
      { href: "/recovery", key: "recovery", icon: Recycle, roles: [...MRF, "processor", "gp_admin"] },
      { href: "/marketplace", key: "marketplace", icon: Store, roles: [...MRF, "processor"] },
    ],
  },
  {
    key: "insights",
    items: [
      { href: "/analytics", key: "analytics", icon: BarChart3, roles: [...ADMINS, "mrf_operator"] },
      { href: "/finance", key: "finance", icon: IndianRupee, roles: [...ADMINS, "mrf_operator"] },
      { href: "/reports", key: "reports", icon: FileText, roles: [...ADMINS, "mrf_operator"] },
    ],
  },
  {
    key: "support",
    items: [
      { href: "/complaints", key: "complaints", icon: MessageSquareWarning, roles: ["gp_admin", "collector", "household", "evaluator"] },
      { href: "/notifications", key: "notifications", icon: Bell, roles: "all" },
      { href: "/help", key: "help", icon: HelpCircle, roles: "all" },
    ],
  },
  {
    key: "admin",
    items: [
      { href: "/users", key: "users", icon: Users, roles: ["gp_admin"] },
      { href: "/audit-logs", key: "auditLogs", icon: ShieldCheck, roles: ["evaluator"] },
      { href: "/settings", key: "settings", icon: Settings, roles: ["gp_admin", "evaluator"] },
      { href: "/profile", key: "profile", icon: Gauge, roles: "all" },
    ],
  },
];

export function canSee(item: NavItem, roles: Role[]): boolean {
  if (item.roles === "all" || roles.includes("super_admin")) return true;
  return item.roles.some((r) => roles.includes(r));
}

export function visibleNav(roles: Role[]): NavSection[] {
  return NAV.map((s) => ({ ...s, items: s.items.filter((i) => canSee(i, roles)) })).filter((s) => s.items.length);
}

export function findNavItem(pathname: string): NavItem | undefined {
  const all = NAV.flatMap((s) => s.items).sort((a, b) => b.href.length - a.href.length);
  return all.find((i) => pathname === i.href || pathname.startsWith(`${i.href}/`));
}
