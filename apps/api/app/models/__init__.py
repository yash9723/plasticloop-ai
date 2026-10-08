"""Import every model so Base.metadata is complete (Alembic, tests, scripts)."""

from app.models.collection import (  # noqa: F401
    CollectionAssignment,
    CollectionEvent,
    CollectionPoint,
    Complaint,
    Household,
    PickupRequest,
    SyncReceipt,
    WasteStream,
    collection_point_streams,
)
from app.models.identity import (  # noqa: F401
    AuditLog,
    Invitation,
    Organization,
    RefreshToken,
    Role,
    SystemSetting,
    User,
    UserMembership,
    Village,
)
from app.models.iot import Calibration, Device, DeviceCredential, DeviceReading  # noqa: F401
from app.models.logistics import Route, RouteStop, Vehicle  # noqa: F401
from app.models.misc import MediaFile, Notification, VisionPrediction, VisionReview  # noqa: F401
from app.models.mrf import (  # noqa: F401
    BatchLineage,
    BatchMovement,
    BatchOperation,
    Facility,
    FacilityIntake,
    MaterialBatch,
    MaterialCategory,
)
from app.models.recovery import (  # noqa: F401
    Expense,
    MaterialListing,
    MaterialOffer,
    Payment,
    ProcessingOutcome,
    ProcessingPartner,
    ProcessingTransfer,
    Sale,
)
