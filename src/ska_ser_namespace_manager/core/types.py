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


class NamespaceStatus(Enum):
    """
    NamespaceStatus lists all namespace statuses
    """

    OK = "ok"
    STALE = "stale"
    FAILING = "failing"
    FAILED = "failed"
    UNSTABLE = "unstable"
    UNKNOWN = "unknown"

    @property
    def value_numeric(self):
        """
        Property that holds the integer value of a status
        """
        status_values = {
            NamespaceStatus.OK: 0,
            NamespaceStatus.STALE: 1,
            NamespaceStatus.FAILING: 2,
            NamespaceStatus.FAILED: 3,
            NamespaceStatus.UNSTABLE: 4,
            NamespaceStatus.UNKNOWN: 5,
        }
        return status_values[self]

    @classmethod
    def from_string(cls, status_str: str):
        """
        Get the enum member corresponding to the given string.

        :param status_str: The string representation of the status.
        :return: The corresponding NamespaceStatus enum member.
        :raises ValueError: If the string does not match any enum member.
        """
        for status in cls:
            if status.value == status_str:
                return status
        raise ValueError(f"'{status_str}' is not a valid {cls.__name__}")
