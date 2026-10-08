from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    audit_logs,
    auth,
    collection_points,
    collections,
    complaints,
    demo,
    devices,
    events,
    facilities,
    finance,
    inventory,
    marketplace,
    health,
    households,
    media,
    notifications,
    organizations,
    pickup_requests,
    processors,
    reports,
    routes,
    settings,
    sync,
    transfers,
    users,
    vehicles,
    vision,
    villages,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
api_router.include_router(villages.router, prefix="/villages", tags=["villages"])
api_router.include_router(households.router, prefix="/households", tags=["households"])
api_router.include_router(collection_points.router, prefix="/collection-points", tags=["collection-points"])
api_router.include_router(pickup_requests.router, prefix="/pickup-requests", tags=["pickup-requests"])
api_router.include_router(collections.router, prefix="/collections", tags=["collections"])
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(complaints.router, prefix="/complaints", tags=["complaints"])
api_router.include_router(media.router, prefix="/media", tags=["media"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(vehicles.router, prefix="/vehicles", tags=["vehicles"])
api_router.include_router(routes.router, prefix="/routes", tags=["routes"])
api_router.include_router(facilities.router, prefix="/facilities", tags=["facilities"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(vision.router, prefix="/vision", tags=["vision"])
api_router.include_router(processors.router, prefix="/processors", tags=["processors"])
api_router.include_router(transfers.router, prefix="/processing-transfers", tags=["processing-transfers"])
api_router.include_router(marketplace.router, prefix="/marketplace", tags=["marketplace"])
api_router.include_router(finance.router, prefix="/finance", tags=["finance"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(audit_logs.router, prefix="/audit-logs", tags=["audit"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(demo.router, prefix="/demo", tags=["demo"])
