# Change Log
All notable changes to this project will be documented in this file.
 
The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## 0.3.0 - 2026-05-18

- **Metrics management refactor**
  - refactored metrics handling around per-process Prometheus registries persisted as owner-specific `.prom` files
  - added reusable Prometheus textfile restore/write helpers for gauges, counters, summaries, histograms, info metrics, and enums
  - changed the public metrics API to merge metrics files from the shared registry path
  - simplified merged metrics loading to read all `.prom` files and ignore files that disappear during merging

- **Namespace check result metrics**
  - added the `namespace_manager_ns_check_total` counter for periodic namespace check success and failure results
  - labelled namespace check result metrics by controller owner and result
  - record namespace check failures when in-process namespace check threads raise exceptions

- **Namespace deletion metrics**
  - added the `namespace_manager_ns_delete_total` counter for deleted namespaces by status
  - record deletion metrics from the action-controller when stale or failed namespaces are deleted
  - added action-controller metrics configuration and metrics registry volume mounting when metrics are enabled

- **Metrics file reconciliation**
  - added a leader-only collect-controller task to delete metrics files for inactive namespace-manager pods
  - discover active API, collect-controller, and action-controller pods before reconciling shared metrics files
  - removed time-based stale metrics file filtering in favour of active pod reconciliation


## 0.2.0 - 2026-04-29

- **Collect-controller namespace checks run in-process**
  - replaced namespace check CronJobs with periodic in-process threads managed by the collect-controller
  - distributed namespace checks across collect-controller replicas and increased the default replica count to `3`
  - changed the default `check-namespace` schedule format from cron syntax to interval syntax, defaulting to `60s`
  - corrected the default collect-controller chart configuration key from `tasks` to `actions`
  - removed the Kubernetes Job-based ownership collection path and its collect-controller RBAC permissions
  - reused a shared `NamespaceCollector` instance across namespace checks instead of instantiating a collector per action

- **Collect-controller StatefulSet migration**
  - changed the collect-controller workload from a Deployment to a StatefulSet with stable ordinal pod names
  - added a headless governing Service and rendered StatefulSet context for collect-controller configuration

- **Collect-controller liveness probe support**
  - added heartbeat-based liveness configuration for collect-controller pods
  - updated the controller to refresh a heartbeat file used by the Helm chart liveness probe

- **Prometheus alert filtering fix**
  - fixed namespace alert matching so Prometheus alerts can also be filtered by optional `datacentre` label
  - added Helm values and configuration support for the Prometheus `datacentre` filter

- **Notification annotation update**
  - replaced the manager-owned namespace owner annotation with the CI/CD notification address annotation for user notifications
  - updated stale, failed, failing, and unstable namespace notifications to use `cicd.skao.int/notificationAddress`

- **Leader election**
  - fixed stale leader lock handling for the upgraded `filelock` dependency without unlinking the shared lock path

- **Dependency and runtime image updates**
  - update ska base images as part of the monthly ST security patches
  - updated python dependencies

## 0.1.6 - 2025-09-11

- **Update base images** 
  - update ska base images as part of the monthly ST security patches

## 0.1.1 - 2025-02-14

- **Address bug and refractor** 
  - failing_resources was not being cleaned after status passed to OK, when comming from UNSTABLE, FAILING or FAILED
  - small refractor of namespace controller

## 0.1.0 - 2025-02-11

- **Prometheus Alert Integration**  
  - Fetches alerts from Prometheus and updates namespace status dynamically.  
  - Parses alerts to identify failing resources (Pods, Deployments, Containers, etc).  
  - Adds a JSON-formatted annotation (`FAILED_RESOURCES`) containing detailed failure information.  

- **Improved Namespace Status Handling**  
  - Fixed issue where namespaces stuck in "OK" state would not transition to UNSTABLE or FAILED. 
  - If Prometheus alerts are unavailable, a **fallback mechanism** checks Kubernetes resources (Deployments, StatefulSets, ReplicaSets).  
  - Ensures that namespaces marked as OK can transition if new issues arise.   

## 0.0.1 - 2024-08-23

- **Initial setup of the repository**
