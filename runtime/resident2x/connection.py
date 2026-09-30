"""Dedicated login, opaque local secret reference; no owner credentials in Resident."""
from pathlib import Path
import psycopg


def connection_factory(config):
    settings = config["database"]
    if not settings["user"].startswith("resident2x_"):
        raise ValueError("dedicated_executor_login_required")
    if settings["sslmode"] not in ("require", "verify-full"):
        raise ValueError("tls_required")
    secret = Path(config["database_password_file"]).resolve()
    if not secret.is_relative_to(Path(config["state_directory"]).resolve()):
        raise ValueError("secret_outside_runtime")

    def connect():
        return psycopg.connect(**settings, password=secret.read_text(encoding="utf-8").strip(),
            connect_timeout=10, application_name="RESIDENT_ADA_2X_HOME01",
            options="-c statement_timeout=15000 -c lock_timeout=5000 -c timezone=UTC")
    return connect
