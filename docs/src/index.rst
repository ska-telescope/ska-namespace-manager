:html_theme.sidebar_secondary.remove:

SKA Namespace Manager
=====================

Pipelines create ephemeral namespaces which sometimes are not deleted correctly,
ending up with a lot of stale namespaces that consume cluster resources. The SKA
Namespace Manager is a Kubernetes operator that watches the namespaces it is
configured to own, decides whether each one is healthy, stale, cancelled or superseded, tells the owner
what is about to happen, and then deletes the namespace when it is no longer needed.


It runs as three cooperating processes, a REST API, a collect controller that
observes and annotates namespaces, and an action controller that notifies and
deletes, all deployed from the Helm chart that ships in this repository.

.. mermaid::
   :alt: Component architecture of the SKA Namespace Manager: the REST API, the
         collect controller and the action controller, the shared volume they
         use for metrics and leader election, and the Kubernetes, Prometheus,
         GitLab, People Database and Slack systems they talk to.

   flowchart LR
       prom["Prometheus"]
       gitlab["GitLab API"]

       subgraph nsm["SKA Namespace Manager (Helm release)"]
           direction TB
           collect["Collect controller<br/><i>StatefulSet</i><br/>adopt · check · annotate"]
           action["Action controller<br/><i>Deployment</i><br/>notify · delete"]
           volume[("Shared ReadWriteMany volume<br/>metrics files · leader lock")]
           api["REST API<br/><i>Deployment</i><br/>/health · /api/people · /api/metrics<br/><i>scraped by Prometheus</i>"]
       end

       k8s["Kubernetes API"]
       ns["Managed namespaces<br/>their manager.cicd.skao.int annotations<br/>hold the lifecycle state"]
       people[("SKAO People Database")]
       slack["Slack"]

       prom -- "firing alerts" --> collect
       gitlab -- "pipeline status" --> collect

       collect -- "annotate status" --> k8s
       action -- "read status, delete" --> k8s
       k8s --> ns

       collect -- "metrics, leader lock" --> volume
       action -- "metrics" --> volume
       volume -- "merged *.prom" --> api
       api -- "ownership lookup" --> people
       action -- "notifications" --> slack

       classDef controller fill:#dbeafe,stroke:#1f6feb,color:#0b2545,font-weight:bold;
       classDef service fill:#ede9fe,stroke:#8250df,color:#2d1065,font-weight:bold;
       classDef platform fill:#eef2f6,stroke:#8b98a5,color:#1c2b36;
       classDef store fill:#fff4e5,stroke:#d97706,color:#7a3e00;
       classDef integration fill:#eaf7ea,stroke:#2da44e,color:#0f3d1f;

       class collect,action controller;
       class api service;
       class k8s platform;
       class ns,people,volume store;
       class prom,gitlab,slack integration;

There is no database and there are no per-check Kubernetes Jobs: the state that
matters lives on the namespace's own annotations, the checks run as threads
inside the collect controller, and the only shared storage is a
``ReadWriteMany`` volume holding metrics files and the leader lock.

.. skao-tools-grid::
   :columns: 3
   :style: feature

   - title: Getting started
     description: Build the image, deploy the chart to a local cluster, and watch a namespace through its lifecycle.
     icon: lightning
     icon-color: pink
     link: howto-run-and-deploy.html

   - title: Reference
     description: Every configuration key, chart value, metric, annotation and default, with its source.
     icon: book
     icon-color: blue
     link: reference-configuration.html

   - title: How it works
     description: Namespace matching, the status state machine, sharding, leader election and metrics.
     icon: gear
     icon-color: teal
     link: explanation-namespace-lifecycle.html

What it does today
------------------

* Deletes CI namespaces once their configured TTL has elapsed.
* Detects unhealthy namespaces from Prometheus alerts, or from Deployment,
  StatefulSet and ReplicaSet replica counts when Prometheus is not configured,
  and deletes them after a settling and a grace period.
* Deletes namespaces whose originating GitLab pipeline was cancelled or
  removed, when the ``cancelled`` check is enabled.
* Deletes older namespaces that a newer deployment of the same branch or merge
  request has superseded, when the ``superseded`` check is enabled.
* Notifies namespace owners on Slack when a namespace becomes unstable,
  failing, cancelled or superseded, and when it is deleted.
* Publishes Prometheus metrics for namespace status, namespace check results
  and namespace deletions.
* Answers ownership lookups from the SKAO People Database through its REST API,
  which is how a namespace label is turned into someone to notify.

.. toctree::
   :hidden:
   :maxdepth: 1

   Getting started <howto-run-and-deploy>
   Reference <reference-configuration>
   How it works <explanation-namespace-lifecycle>
