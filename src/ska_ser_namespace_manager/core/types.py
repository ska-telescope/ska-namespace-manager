"""
types provides type declaration to be used in the API and
as DTOs in database operations
"""

from enum import Enum


class CicdAnnotations(str, Enum):
    """
    CicdAnnotations describes the used cicd annotations
    """

    JOB_URL = "cicd.skao.int/jobUrl"

    def __str__(self):
        return self.value


class NamespaceAnnotations(str, Enum):
    """
    NamespaceAnnotations describes all known annotations
    so that they are easy to quantify and change
    """

    MANAGED = "manager.cicd.skao.int/managed"
    NAMESPACE = "manager.cicd.skao.int/namespace"
    ACTION = "manager.cicd.skao.int/action"
    STATUS = "manager.cicd.skao.int/status"
    STATUS_TS = "manager.cicd.skao.int/status_timestamp"
    STATUS_TIMEFRAME = "manager.cicd.skao.int/status_timeframe"
    STATUS_FINALIZE_AT = "manager.cicd.skao.int/status_finalize_at"
    OWNER = "manager.cicd.skao.int/owner"
    FAILING_RESOURCES = "manager.cicd.skao.int/failing_resources"
    NOTIFIED_TS = "manager.cicd.skao.int/notified_timestamp"
    NOTIFIED_STATUS = "manager.cicd.skao.int/notified_status"

    def __str__(self):
        return self.value
