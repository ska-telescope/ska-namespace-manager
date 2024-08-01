"""
namespace provides core namespace DTO and supporting functions
"""

import re
from typing import Dict, List, Optional, TypeVar

from pydantic import BaseModel

FORBIDDEN_NAMESPACES = [
    "kube-system",
    "kube-public",
    "kube-node-lease",
    "default",
]


class Namespace(BaseModel):
    """
    Namespace is Kubernetes API DTO to abstract business logic
    from the Kubernetes API specificities
    """

    name: str
    labels: Optional[Dict[str, str]] = None
    annotations: Optional[Dict[str, str]] = None

    def model_post_init(self, _):
        if self.labels is None:
            self.labels = {}

        if self.annotations is None:
            self.annotations = {}


class NamespaceMatchingOptions(BaseModel):
    """
    NamespaceMatchingOptions holds label and annotation information
    to match namespaces instead of just the name
    """

    annotations: Optional[Dict[str, str]] = None
    labels: Optional[Dict[str, str]] = None


class NamespaceMatcher(BaseModel):
    """
    NamespaceMatcher holds the list (matching instructions) on
    all namespaces. Namespace matching happens
    with the following precedence:

    - all > any > names

    * names: List of names (regex support) to match
    * any: Match any of the labels (or'ed)
    * all: Match any of the labels (and'ed)
    """

    names: Optional[List[str]] = None
    any: Optional[List[NamespaceMatchingOptions]] = None
    all: Optional[List[NamespaceMatchingOptions]] = None


T = TypeVar("T", bound=NamespaceMatcher)


def match_condition(
    namespace: Namespace, condition: NamespaceMatchingOptions
) -> bool:
    """
    Check if namespace matches all provided conditions
    """
    return all(
        (
            all(
                namespace.annotations.get(key) == value
                for key, value in (condition.annotations or {}).items()
            ),
            all(
                namespace.labels.get(key) == value
                for key, value in (condition.labels or {}).items()
            ),
        )
    )


def match_namespace(configs: List[T], namespace: Namespace) -> T | None:
    """
    Matches a namespace against a list of namespace configurations, returning
    the best match. Predence is all > any > names given how specific each of
    these values are.

    :param configs: List of configurations to evaluate
    :param namespace: Namespace details
    :return: Best matching configuration, if found
    """
    if namespace is None or configs is None or len(configs) == 0:
        return None

    best_matching_config = None
    best_score = 0
    for config in configs:
        score = 0
        if config.names:
            name_match = any(
                re.match(pattern, namespace.name) for pattern in config.names
            )
            if name_match:
                score += 1

        if config.any:
            any_match = (
                any(
                    (match_condition(namespace, condition))
                    for condition in config.any
                )
                if config.any
                else False
            )

            if any_match:
                score += 2

        all_match = (
            all(
                (match_condition(namespace, condition))
                for condition in config.all
            )
            if config.all
            else False
        )

        if all_match:
            score += 4  # Highest priority

        # Determine if this configuration is the best match so far
        if score > best_score:
            best_score = score
            best_matching_config = config

    return best_matching_config
