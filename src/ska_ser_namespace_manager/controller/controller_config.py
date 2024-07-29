"""
controller_config centralizes all the shared configurations
between controllers
"""

from pydantic import BaseModel


class KubernetesContext(BaseModel):
    """
    KubernetesContext holds configurations regarding the deployment
    context
    """

    matchLabels: dict[str, str]
    namespace: str
    service_account: str


class ControllerConfig(BaseModel):
    """
    LeaderElectionConfig holds configurations for controller leader
    election process
    """

    context: KubernetesContext
