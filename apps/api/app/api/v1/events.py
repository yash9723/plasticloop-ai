"""Server-sent events: Postgres NOTIFY → browser. The client reads it with fetch() streaming (Bearer header, no token in URL)."""

import json

import psycopg
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.security.deps import DB, CurrentUser
from app.services.telemetry import EVENT_CHANNEL

router = APIRouter()
KEEPALIVE_S = 15


def _dsn() -> str:
    return settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@router.get("/stream", summary="Live operational events (text/event-stream)")
def stream(principal: CurrentUser, db: DB):
    scope = principal.scope
    allowed = {str(v) for v in scope.village_ids}
    # Release the request's DB session now: FastAPI would otherwise keep it (and its locks) open for the whole stream.
    db.close()

    def events():
        # ponytail: one DB connection + one worker thread per open stream. Fine for a panchayat-sized deployment;
        # move to a single shared LISTEN connection fanning out to asyncio queues if concurrent viewers grow past ~50.
        with psycopg.connect(_dsn(), autocommit=True) as conn:
            conn.execute(f"LISTEN {EVENT_CHANNEL}")
            yield "retry: 5000\n: connected\n\n"
            while True:
                for note in conn.notifies(timeout=KEEPALIVE_S, stop_after=20):
                    try:
                        data = json.loads(note.payload)
                    except ValueError:
                        continue
                    if not scope.sees_all and data.get("village_id") not in allowed:
                        continue
                    yield f"event: {data.get('kind', 'message')}\ndata: {note.payload}\n\n"
                yield ": keepalive\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             # no-transform stops the Next.js proxy (and other gzip layers) from buffering the stream.
                             headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"})
