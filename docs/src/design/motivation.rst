Motivation
==========

In a production cluster, administrators have good knowledge on what namespaces are deployed, what resources each namespace requires, and nothing gets deployed without their avail. The cluster also has a **predictable** resource usage - even when it spikes. In the case of a CICD cluster with limited resources, running jobs that are very heterogeneous in their requirements, scheduling and execution time, makes the cluster vulnerable to:

* Users/teams claiming too many resources, being CPU/Memory or simply Gitlab Runner jobs
* Stale/Failing deployments wasting resources
* Resource/Job exhaustion

Kubernetes doesn't provide an out-of-the-box solution for this, so we need a custom implementation. The goal of SKA Namespace Manager is to be able to optimize the usage of the cluster resources and provide fair share to every user. In the spirit of visibility and predictability, is expected that it communicates to the affected users any operations done to their environments. This will allow developers to be more aware of what is going on in the background.