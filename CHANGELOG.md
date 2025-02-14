# Change Log
All notable changes to this project will be documented in this file.
 
The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).


## [Unreleased] - 2024-07-18

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