from enum import StrEnum


class RoleKey(StrEnum):
    SUPER_ADMIN = "super_admin"
    GP_ADMIN = "gp_admin"
    COLLECTOR = "collector"
    DRIVER = "driver"
    MRF_OPERATOR = "mrf_operator"
    PROCESSOR = "processor"
    HOUSEHOLD = "household"
    EVALUATOR = "evaluator"


class OrgType(StrEnum):
    PLATFORM = "platform"
    GRAM_PANCHAYAT = "gram_panchayat"
    MRF_OPERATOR = "mrf_operator"
    PROCESSOR = "processor"
    BUYER = "buyer"


class DataOrigin(StrEnum):
    LIVE = "live"
    DEMO_SEED = "demo_seed"
    SIMULATED = "simulated"


class MeasurementSource(StrEnum):
    DEVICE_MEASURED = "device_measured"
    MANUAL_ENTRY = "manual_entry"
    SIMULATED_SENSOR = "simulated_sensor"
    ESTIMATED = "estimated"


class PointStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class PickupStatus(StrEnum):
    SUBMITTED = "submitted"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ComplaintStatus(StrEnum):
    OPEN = "open"
    ASSIGNED = "assigned"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    CLOSED = "closed"


class AssignmentStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    MISSED = "missed"
    SKIPPED = "skipped"


class ReviewStatus(StrEnum):
    OK = "ok"
    FLAGGED = "flagged"
    RESOLVED = "resolved"


class SyncReceiptStatus(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    REJECTED = "rejected"


class DeviceType(StrEnum):
    WEIGHING_SCALE = "weighing_scale"
    FILL_SENSOR = "fill_sensor"
    COMBO_NODE = "combo_node"
    CAMERA = "camera"


class ConnectionStatus(StrEnum):
    NEVER_SEEN = "never_seen"
    ONLINE = "online"
    STALE = "stale"
    OFFLINE = "offline"


class CalibrationStatus(StrEnum):
    UNCALIBRATED = "uncalibrated"
    CALIBRATED = "calibrated"
    DUE = "due"
    FAILED = "failed"


class ReadingQuality(StrEnum):
    OK = "ok"
    OUT_OF_RANGE = "out_of_range"
    NEGATIVE_DRIFT = "negative_drift"
    SENSOR_ERROR = "sensor_error"
    CLOCK_SKEW = "clock_skew"


class VehicleType(StrEnum):
    AUTO_RICKSHAW = "auto_rickshaw"
    E_CART = "e_cart"
    TRACTOR_TROLLEY = "tractor_trolley"
    MINI_TRUCK = "mini_truck"
    OTHER = "other"


class RouteStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class StopStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class FacilityType(StrEnum):
    MRF = "mrf"
    PWMU = "pwmu"


class BatchStatus(StrEnum):
    ACTIVE = "active"
    DEPLETED = "depleted"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    SUSPECTED = "suspected"
    VERIFIED_WITH_EVIDENCE = "verified_with_evidence"
    VERIFICATION_REJECTED = "verification_rejected"


class MovementType(StrEnum):
    INTAKE = "intake"
    SORT_OUT = "sort_out"
    SORT_IN = "sort_in"
    SPLIT_OUT = "split_out"
    SPLIT_IN = "split_in"
    MERGE_OUT = "merge_out"
    MERGE_IN = "merge_in"
    TRANSFER_OUT = "transfer_out"
    TRANSFER_RETURN = "transfer_return"
    LOSS = "loss"
    DISPOSAL = "disposal"
    ADJUSTMENT = "adjustment"


class TransferStatus(StrEnum):
    ALLOCATED = "allocated"
    DISPATCHED = "dispatched"
    RECEIVED = "received"
    ACCEPTED = "accepted"
    PARTIALLY_ACCEPTED = "partially_accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OutcomeType(StrEnum):
    ACCEPTED_FOR_PROCESSING = "accepted_for_processing"
    RECYCLED_WITH_EVIDENCE = "recycled_with_evidence"
    RECOVERED_DOCUMENTED_PROCESS = "recovered_documented_process"
    REJECTED = "rejected"
    AWAITING_CONFIRMATION = "awaiting_confirmation"


class EvidenceStatus(StrEnum):
    NONE = "none"
    SUBMITTED = "submitted"
    REVIEWED_ACCEPTED = "reviewed_accepted"
    REVIEWED_REJECTED = "reviewed_rejected"


class DocumentationStatus(StrEnum):
    NOT_SUBMITTED = "not_submitted"
    SUBMITTED = "submitted"
    REVIEWED_VERIFIED = "reviewed_verified"
    REVIEWED_REJECTED = "reviewed_rejected"


class ListingStatus(StrEnum):
    OPEN = "open"
    RESERVED = "reserved"
    SOLD = "sold"
    WITHDRAWN = "withdrawn"


class OfferStatus(StrEnum):
    QUOTE_REQUESTED = "quote_requested"
    OFFERED = "offered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    CANCELLED = "cancelled"


class ExpenseCategory(StrEnum):
    COLLECTION_LABOR = "collection_labor"
    FUEL_VEHICLE = "fuel_vehicle"
    TRANSPORT = "transport"
    EQUIPMENT_MAINTENANCE = "equipment_maintenance"
    FACILITY_OPERATIONS = "facility_operations"
    PROCESSING_FEES = "processing_fees"
    OTHER = "other"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class MediaPurpose(StrEnum):
    COLLECTION_PHOTO = "collection_photo"
    COMPLAINT_PHOTO = "complaint_photo"
    VISION_SAMPLE = "vision_sample"
    TRANSFER_RECEIPT = "transfer_receipt"
    OUTCOME_EVIDENCE = "outcome_evidence"
    VERIFICATION_EVIDENCE = "verification_evidence"
    PROCESSOR_DOCUMENT = "processor_document"
    INVOICE = "invoice"
    OTHER = "other"


class VisionAdapterKind(StrEnum):
    TRAINED = "trained"
    DEMO_HEURISTIC = "demo_heuristic"
    MANUAL_ONLY = "manual_only"


VISION_LABELS = (
    "rigid_plastic",
    "flexible_plastic",
    "suspected_multilayer_packaging",
    "paper_cardboard",
    "metal",
    "other_unknown",
)
