"""
api_config centralizes all the configuration loading for the
api component
"""

import os
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from ska_ser_namespace_manager.metrics.metrics_config import MetricsConfig


class GoogleServiceAccount(BaseModel):
    """
    GoogleServiceAccount holds service account information to be
    able to interact with the People's database. The identifying and
    secret fields are optional so that a disabled PeopleDatabaseConfig
    (and the empty credentials skeleton rendered by the Helm chart) can
    validate without supplying real credentials.
    """

    type: str = "service_account"
    project_id: Optional[str] = None
    private_key_id: Optional[str] = None
    private_key: Optional[str] = None
    client_email: Optional[str] = None
    client_id: Optional[str] = None
    universe_domain: str = "googleapis.com"
    auth_uri: str = "https://accounts.google.com/o/oauth2/auth"
    token_uri: str = "https://oauth2.googleapis.com/token"
    auth_provider_x509_cert_url: str = "https://www.googleapis.com/oauth2/v1/certs"
    client_x509_cert_url: Optional[str] = None


class PeopleDatabaseConfig(BaseModel):
    """
    PeopleDatabaseConfig holds all of the configurations to be able
    to interact with the Peopledatabase. When ``enabled`` is False the
    credentials and spreadsheet_id may be omitted; when enabled they are
    required.
    """

    credentials: Optional[GoogleServiceAccount] = None
    spreadsheet_id: Optional[str] = None
    spreadsheet_range: str = "System Team API!A2:Z1001"
    cache_ttl: int = 3600
    enabled: bool = True

    def model_post_init(self, _):
        if not self.enabled:
            return

        missing = []
        if not self.spreadsheet_id:
            missing.append("spreadsheet_id")

        if self.credentials is None:
            missing.append("credentials")
        else:
            for field in ("project_id", "private_key", "client_email"):
                if not getattr(self.credentials, field):
                    missing.append(f"credentials.{field}")

        if missing:
            raise ValueError(
                "People database is enabled but the following required "
                f"configuration is missing: {', '.join(missing)}. Set "
                "people_database.enabled to false to run without it."
            )


class APIConfig(BaseModel):
    """
    APIConfig is a singleton class to provide abstraction from
    configuration loading for the API
    """

    https_port: int = 9443
    https_enabled: bool = False
    pki_path: str = "/etc/pki"
    http_port: int = 8080
    ca_path: Optional[str] = None
    cert_path: Optional[str] = None
    key_path: Optional[str] = None
    people_database: PeopleDatabaseConfig = Field(
        default_factory=lambda: PeopleDatabaseConfig(enabled=False)
    )
    metrics: Optional[MetricsConfig] = MetricsConfig()

    @model_validator(mode="before")
    @classmethod
    def disable_empty_people_database(cls, data):
        """
        Treats an explicitly empty people database mapping as disabled.
        """
        if isinstance(data, dict) and data.get("people_database") == {}:
            data = dict(data)
            data["people_database"] = {"enabled": False}

        return data

    def model_post_init(self, _):
        if self.https_enabled:
            self.ca_path = os.path.join(self.pki_path, "ca.crt")
            self.cert_path = os.path.join(self.pki_path, "tls.crt")
            self.key_path = os.path.join(self.pki_path, "tls.key")
