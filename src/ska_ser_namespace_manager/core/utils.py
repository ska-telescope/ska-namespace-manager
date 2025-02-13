"""
utils provides utility classes and functions
"""

import base64
import datetime
import json
import re
from typing import Any, Tuple

import pytz
from starlette.requests import Request

UNITS = {
    "s": "seconds",
    "m": "minutes",
    "h": "hours",
    "d": "days",
    "w": "weeks",
}


ALERT_SUGGESTIONS = {
    "KubePodNotReady": "If the pod state is Running but not ready then readiness probe fails. If the pod state is Pending then pod can not be created. Investigate the pod's logs in Kibana and health status and pod events in Headlamp to understand why it isn't ready.",  # pylint: disable=line-too-long  # noqa: E501
    "KubePodCrashLooping": "Pod is in CrashLoop which means the app dies or is unresponsive and kubernetes tries to restart it automatically. This may be caused by configuration issues, missing dependencies, or failing health checks. Check the pod's logs in Kibana and monitor the container's health in Headlamp to identify the root cause.",  # pylint: disable=line-too-long  # noqa: E501
    "KubeDeploymentReplicasMismatch": "The number of replicas in the deployment does not match the desired replica count. This could be due to failed pod creation or issues with the deployment's configuration. Review the deployment configuration to ensure that the replica count is correctly set. Check if there are any errors in the deployment logs or pod status that could explain why some replicas are not being created.",  # pylint: disable=line-too-long  # noqa: E501
    "KubeStatefulSetReplicasMismatch": "The number of replicas in the StatefulSet does not match the desired replica count. Check the StatefulSet's configuration and ensure that the correct number of replicas is set. Investigate whether there are any issues with pod creation that could prevent the StatefulSet from scaling properly.",  # pylint: disable=line-too-long  # noqa: E501
    "KubeJobNotCompleted": "The job has not completed successfully within the expected time. This could be due to issues with the job's execution. Check the status of the job and review the logs in Kibana. Ensure that the job is not stuck in a pending state and that there are no resource bottlenecks using Headlamp.",  # pylint: disable=line-too-long  # noqa: E501
    "CPUThrottlingHigh": "High CPU throttling is occurring. Please make sure cpu requests are set correctly by investigating Grafana dashboards",  # pylint: disable=line-too-long  # noqa: E501
    "KubeDeploymentGenerationMismatch": "Deployment generation mismatch due to possible roll-back.",  # pylint: disable=line-too-long  # noqa: E501
    "KubeDeploymentRolloutStuck": "The deployment's rollout is stuck. A stuck deployment means that the expected number of replicas cannot be created or updated, which could be caused by various issues such as resource constraints, invalid configuration, or failure to pull images. Check the status of the deployment in Kibana or Grafana. Review the deployment's configuration for potential issues.",  # pylint: disable=line-too-long  # noqa: E501
    "KubeStatefulSetUpdateNotRolledOut": "A StatefulSet update is stuck, likely due to pod scheduling issues, failed readiness probes, PVC binding problems, or resource constraints. Check pod and StatefulSet logs in Kibana for failures.",  # pylint: disable=line-too-long  # noqa: E501
    "KubeContainerWaiting": "The container in the pod is stuck in the 'waiting' state for too long. This could indicate issues such as a missing image or dependencies that are not available. Investigate the reason why the container is waiting by checking the pod's logs in Kibana. Ensure that the container image is accessible and the required resources are available.",  # pylint: disable=line-too-long  # noqa: E501
    "KubeJobFailed": "Investigate the job logs in Kibana and check the job configuration for errors.",  # pylint: disable=line-too-long  # noqa: E501
    "KubePersistentVolumeInodesFillingUp": "The Persistent Volume is running low on inodes. Create an STS ticket stating this situation.",  # pylint: disable=line-too-long  # noqa: E501
    "KubePersistentVolumeFillingUp": "The Persistent Volume (PV) is running very low on available space. Create an STS ticket stating this situation.",  # pylint: disable=line-too-long  # noqa: E501
    "KubeQuotaExceeded": "The namespace exceeded its resource quota. Create an STS ticket stating this situation.",  # pylint: disable=line-too-long  # noqa: E501
}


class Singleton(type):
    """
    Singleton implements the singleton pattern to be used as a
    metaclass for classes that are singletons
    """

    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(
                *args, **kwargs
            )

        return cls._instances[cls]


def deserialize_request(request: Request):  # pragma: no cover
    """
    Deserializes request into useful information for debugging

    :param request: Request that originated an debuggable event
    """
    return json.dumps(
        {
            "url": str(request.url),
            "headers": {
                header[0]: header[1] for header in request.headers.items()
            },
        },
        indent=4,
    )


def parse_timedelta(v: Any) -> datetime.timedelta:
    """
    Parses string to timedelta

    :param v: Input time delta
    :return: Timedelta as datetime.timedelta
    """
    timedelta = str(v)
    return datetime.timedelta(
        **{
            UNITS.get(m.group("unit").lower(), "seconds"): float(
                m.group("val")
            )
            for m in re.finditer(
                r"(?P<val>\d+(\.\d+)?)(?P<unit>[smhdw])",
                timedelta.replace(" ", ""),
                flags=re.I,
            )
        }
    )


def format_utc(date: datetime.datetime) -> str:
    """
    Formats date as UTC in ISO8601 format

    :param date: Date to format
    :return: Date in utc
    """
    return date.replace(tzinfo=pytz.UTC).isoformat().replace("+00:00", "Z")


def utc(delta: datetime.timedelta = datetime.timedelta(microseconds=0)) -> str:
    """
    Gets a date as UTC in ISO8601 format

    :param delta: Delta to add to now
    :return: Date in utc
    """
    return format_utc((datetime.datetime.now(pytz.UTC) + delta))


def encode_slack_address(name: str, slack_id: str) -> str:
    """
    Encodes the slack id and user name in base64 into an
    "address"

    :param slack_id: User name
    :param slack_id: User slack id
    :return: Encoded address
    """
    return base64.b64encode(f"{name}::{slack_id}".encode("utf-8")).decode(
        "utf-8"
    )


def decode_slack_address(address: str) -> Tuple[str, str]:
    """
    Decodes the slack id and user name from base64

    :param address: Address to decode
    :return: Name and slack id
    """
    if address in [None, ""]:
        return None, None

    return tuple(base64.b64decode(address).decode("utf-8").split("::"))
