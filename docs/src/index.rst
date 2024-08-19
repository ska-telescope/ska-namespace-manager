SKA Namespace Manager
=====================

SKA Namespace Manager is a tool designed to efficiently manage namespaces in a Kuberentes cluster. The main goal is to be able to provide fair usage quotasto the multiple users of the cluster, as well as to maintain efficient use of it.

What the SKA Namespace Manager can do now:

  * Nothing

What's on the roadmap for SKA Namespace Manager:

  * Cleanup CI namespaces after their pre-defined or default TTL
  * Terminate failing CI namespaces
  * Terminate duplicate CI namespaces (same commit or merge request)
  * Notify namespace owners of their namespaces' status changes

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