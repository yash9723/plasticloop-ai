/**
 * Frontend aliases for API contract types. Every alias points at the OpenAPI-generated schema in
 * @plasticloop/shared-schemas (regenerate with `pnpm gen:api`), so backend changes surface as type errors here.
 */
import type { Schema } from "@plasticloop/shared-schemas";

export type NotificationItem = Schema<"NotificationOut">;
export type Village = Schema<"VillageOut">;
export type VillageDetail = Schema<"VillageDetail">;
export type VillagePublic = Schema<"VillagePublic">;
export type Organization = Schema<"OrganizationOut">;
export type UserRow = Schema<"UserOut">;
export type UserBrief = Schema<"UserBrief">;
export type WasteStream = Schema<"WasteStreamOut">;
export type CollectionPoint = Schema<"CollectionPointOut">;
export type CollectionPointBrief = Schema<"CollectionPointBrief">;
export type Household = Schema<"HouseholdOut">;
export type PickupRequest = Schema<"PickupRequestOut">;
export type CollectionEvent = Schema<"CollectionEventOut">;
/** Body of an offline collection event (same fields as the online create endpoint, minus the client id). */
export type CollectionPayload = Omit<Schema<"CollectionCreateIn">, "event_id">;
export type Receipt = Schema<"ReceiptOut">;
export type MyTasks = Schema<"MyTasksOut">;
export type TaskStop = Schema<"TaskStop">;
export type SyncResult = Schema<"SyncEventResult">;
export type SyncReceipt = Schema<"SyncReceiptOut">;
export type Complaint = Schema<"ComplaintOut">;
export type Media = Schema<"MediaOut">;
export type InvitationPublic = Schema<"InvitationPublic">;
export type MaterialCategory = Schema<"MaterialCategoryOut">;
export type SystemSettingItem = Schema<"SystemSettingItem">;
export type Device = Schema<"DeviceOut">;
export type DeviceCreated = Schema<"DeviceCreated">;
export type DeviceReading = Schema<"ReadingOut">;
export type Calibration = Schema<"CalibrationOut">;
export type Vehicle = Schema<"VehicleOut">;
export type RouteRow = Schema<"RouteOut">;
export type RouteDetail = Schema<"RouteDetail">;
export type RouteStop = Schema<"StopOut">;
export type RouteCandidate = Schema<"CandidateOut">;
export type Facility = Schema<"FacilityOut">;
export type Intake = Schema<"IntakeOut">;
export type MassBalance = Schema<"MassBalanceOut">;
export type CategoryStock = Schema<"CategoryStock">;
export type Batch = Schema<"BatchOut">;
export type BatchDetail = Schema<"BatchDetail">;

/** Response of POST /routes/plan (a plain dict on the API side). */
export interface PlanStop {
  sequence: number;
  collection_point_id: string;
  code: string;
  name: string;
  lat: number;
  lng: number;
  arrival_s: number;
  eta: string;
  expected_kg: number;
  load_after_kg: number;
  leg_m: number;
  load_basis: string;
  reasons: string[];
  emergency: boolean;
}
export interface PlanRoute {
  vehicle_id: string;
  vehicle_name: string;
  registration_no: string;
  capacity_kg: number;
  distance_m: number;
  duration_s: number;
  load_kg: number;
  utilization_pct: number;
  cost_estimate_paise: number;
  stops: PlanStop[];
  path: [number, number][];
}
export interface PlanResult {
  plan_id: string | null;
  distance_basis: "osrm_road" | "haversine_estimate";
  solver: string;
  solver_status: string;
  warnings: string[];
  routes: PlanRoute[];
  dropped: { collection_point_id: string; code: string; name: string; reason: string; expected_kg: number }[];
  facility: { id: string; name: string; lat: number; lng: number } | null;
  totals: {
    candidates: number;
    stops_planned: number;
    stops_dropped: number;
    distance_m: number;
    baseline_distance_m: number | null;
    savings_pct: number | null;
    expected_load_kg: number;
  };
  saved_route_ids: string[];
  assumptions: { avg_speed_kmph: number; service_time_min: number; cost_per_km_paise: number; baseline: string };
}
export type VisionPrediction = Schema<"PredictionOut">;
export type Partner = Schema<"PartnerOut">;
export type Transfer = Schema<"TransferOut">;
export type TransferDetail = Schema<"TransferDetail">;
export type Outcome = Schema<"OutcomeOut">;
export type Listing = Schema<"ListingOut">;
export type SaleRow = Schema<"SaleOut">;
export type ExpenseRow = Schema<"ExpenseOut">;
export type AuditEntry = Schema<"AuditOut">;
