from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIR = Path(__file__).resolve().parents[2]  # apps/api (or /app in the container)
REPO_ROOT = API_DIR.parents[1] if len(API_DIR.parents) >= 2 else API_DIR


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env", API_DIR / ".env"), extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    demo_mode: bool = True

    database_url: str = "postgresql+psycopg://plasticloop:change-me-dev-only@localhost:5432/plasticloop"
    test_database_url: str = "postgresql+psycopg://plasticloop:change-me-dev-only@localhost:5432/plasticloop_test"

    jwt_secret: str = "dev-only-change-me-to-a-long-random-string-of-64-chars"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:3000"

    upload_dir: Path = REPO_ROOT / "data" / "uploads"
    max_upload_mb: int = 5
    media_url_ttl_s: int = 600

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_service_user: str = "plasticloop-service"
    mqtt_service_password: str = "dev-only-mqtt-service-password"
    mqtt_passwd_file: Path = REPO_ROOT / "infra" / "mosquitto" / "auth" / "passwd"
    demo_device_secret: str = "dev-only-demo-device-secret"

    osrm_url: str = ""
    routing_avg_speed_kmph: float = 25.0
    routing_time_limit_s: int = 5

    vision_mode: Literal["auto", "trained", "demo", "manual"] = "auto"
    vision_model_path: Path = API_DIR / "models" / "packaging-cls.pt"

    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def demo_enabled(self) -> bool:
        return self.demo_mode and self.environment != "production"

    @field_validator("database_url", "test_database_url")
    @classmethod
    def _psycopg_driver(cls, v: str) -> str:
        # Hosting providers (Render, Heroku-style) hand out postgres:// or postgresql:// URLs.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.environment == "production":
            problems = []
            if self.demo_mode:
                problems.append("DEMO_MODE must be false when ENVIRONMENT=production")
            if self.jwt_secret.startswith("dev-only") or len(self.jwt_secret) < 32:
                problems.append("JWT_SECRET must be a strong secret (>=32 chars) in production")
            if not self.cookie_secure:
                problems.append("COOKIE_SECURE must be true in production (HTTPS)")
            if self.mqtt_service_password.startswith("dev-only"):
                problems.append("MQTT_SERVICE_PASSWORD must be changed in production")
            if problems:
                raise ValueError("; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
