SKA Namespace Manager
=====================

SKA Namespace Manager is a tool designed to efficiently manage namespaces in a Kubernetes cluster. The main goal is to provide fair usage quotas to multiple cluster users while maintaining efficient resource usage.

What the SKA Namespace Manager can do now:

  * Cleanup CI namespaces after their pre-defined or default TTL
  * Terminate failing CI namespaces
  * Notify namespace owners of their namespaces' status changes

What's on the roadmap for SKA Namespace Manager:
  * Terminate duplicate CI namespaces (same commit or merge request)


The `SKA Namespace Manager
<https://gitlab.com/ska-telescope/ska-ser-namespace-manager.git>`_ aims at providing efficient and fair usage of the resources of the CICD Kubernetes cluster.

.. toctree::
  :maxdepth: 1
  :caption: Design

  design/motivation
  design/overview

.. toctree::
  :maxdepth: 1
  :caption: README

  README.md
