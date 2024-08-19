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

    namespace: str
    service_account: str
    image: str
    config_path: str
    config_secret: str


class ControllerConfig(BaseModel):
    """
    LeaderElectionConfig holds configurations for controller leader
    election process
    """

    context: KubernetesContext
