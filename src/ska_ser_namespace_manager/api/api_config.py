"""
api_config centralizes all the configuration loading for the
api component
"""

import os
from typing import Optional

from pydantic import BaseModel

from ska_ser_namespace_manager.metrics.metrics_config import MetricsConfig


class GoogleServiceAccount(BaseModel):
    """
    GoogleServiceAccount holds service account information to be
    able to interact with the People's database
    """

    type: str = "service_account"
    project_id: str
    private_key_id: str
    private_key: str
    client_email: str
    client_id: str
    universe_domain: str = "googleapis.com"
    auth_uri: str = "https://accounts.google.com/o/oauth2/auth"
    token_uri: str = "https://oauth2.googleapis.com/token"
    auth_provider_x509_cert_url: str = (
        "https://www.googleapis.com/oauth2/v1/certs"
    )
    client_x509_cert_url: str


class PeopleDatabaseConfig(BaseModel):
    """
    PeopleDatabaseConfig holds all of the configurations to be able
    to interact with the Peopledatabase
    """

    credentials: GoogleServiceAccount
    spreadsheet_id: str
    spreadsheet_range: str = "System Team API!A2:Z1001"
    cache_ttl: int = 3600
    enabled: bool = True


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
    people_database: PeopleDatabaseConfig = None
    metrics: Optional[MetricsConfig] = MetricsConfig()

    def model_post_init(self, _):
        if self.https_enabled:
            self.ca_path = os.path.join(self.pki_path, "ca.crt")
            self.cert_path = os.path.join(self.pki_path, "tls.crt")
            self.key_path = os.path.join(self.pki_path, "tls.key")
