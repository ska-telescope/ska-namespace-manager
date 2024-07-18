"""
api_config centralizes all the configuration logging for the
api component
"""

import json
import os

import yaml
from pydantic import BaseModel

from ska_ser_namespace_manager.core.config import Config


class GoogleServiceAccount(BaseModel):
    """
    GoogleServiceAccount holds service account information to be
    able to interact with the People's database
    """

    type: str
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
    spreadsheet_range: str = "A2:Z1001"
    cache_ttl: int = 3600


class APIConfig(Config):
    """
    APIConfig is a singleton class to provide abstraction from
    configuration loading for the API
    """

    https_port: int
    https_enabled: bool
    pki_path: str
    http_port: int
    ca_path: str = None
    cert_path: str = None
    key_path: str = None

    people_database: PeopleDatabaseConfig

    def load(self):
        with open(self.config_path, encoding="utf-8") as config_data:
            config = yaml.safe_load(config_data)
            self.https_port = int(config.get("httpsPort", 9443))
            self.https_enabled = config.get("httpsEnabled", False)
            self.pki_path = config.get("pkiPath", "/etc/pki")
            self.http_port = int(config.get("httpPort", 8080))
            self.people_database = PeopleDatabaseConfig(
                **config.get("people_db", {})
            )

        if self.https_enabled:
            self.ca_path = os.path.join(self.pki_path, "ca.crt")
            self.cert_path = os.path.join(self.pki_path, "tls.crt")
            self.key_path = os.path.join(self.pki_path, "tls.key")

    def __str__(self) -> str:
        return json.dumps(
            {
                "https_port": self.https_port,
                "https_enabled": self.https_enabled,
                "pki_path": self.pki_path,
                "http_port": self.http_port,
                "ca_path": self.ca_path,
                "cert_path": self.cert_path,
                "key_path": self.key_path,
            }
        )
