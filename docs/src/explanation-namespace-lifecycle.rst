How namespace lifecycle management works
========================================

Why a namespace manager exists
------------------------------

The workloads in a CI/CD cluster are heterogeneous in their requirements, scheduling and runtime, so the cluster 
is exposed to users and teams claiming too many resources, stale and failing deployments holding resources nobody 
is using any more, and outright resource or job exhaustion.

The goal of the namespace manager is to optimise cluster usage and give every user a fair share. 
Because the manager deletes other people's namespaces, developers are notified when their environments are removed.

The three components of the namespace manager
---------------------------------------------

The Helm chart deploys three processes from the same image, each started with a
different entrypoint script and its own configuration Secret.

.. list-table::
   :header-rows: 1
   :widths: 20 20 60

   * - Component
     - Workload
     - Responsibility
   * - REST API
     - ``Deployment``
     - Serves ``/health/*`` probes, ownership lookups against the SKAO People
       Database under ``/api/people``, and the merged Prometheus metrics under
       ``/api/metrics``.
   * - Collect controller
     - ``StatefulSet``
     - Finds namespaces that match its configuration, marks them as managed,
       runs a periodic health check per namespace, and writes the resulting
       status onto the namespace as annotations.
   * - Action controller
     - ``Deployment``
     - Reads those annotations, notifies owners on Slack, and deletes
       namespaces whose status has been ``stale``, ``cancelled`` or ``superseded`` for long enough.

Neither controller talks to the other. The namespace itself is the shared
state: the collect controller writes ``manager.cicd.skao.int/*`` annotations,
the action controller reads them. That keeps the two loops independent, either
can be restarted, scaled or temporarily broken.

Which namespaces are managed
----------------------------

Each controller is configured with a list of *matchers*. A namespace can be
selected by name (regular expressions, matched in full), by ``any`` of a set of
label/annotation conditions, or by ``all`` of them. Every configuration entry
that matches is scored — ``names`` scores 1, ``any`` scores 2, ``all`` scores 4
— and the highest-scoring entry wins, so ``all`` beats ``any`` beats ``names``.
The winning entry supplies the TTL, the periods, the checks and, for the action
controller, the per-status delete and notify behaviour.

The collect controller's leader polls for namespaces that do not yet carry
``manager.cicd.skao.int/managed=true``, matches them, and adopts the ones that
match by annotating ``managed=true`` and ``status=unknown``. From that moment
the namespace has a lifecycle.

The status state machine
------------------------

.. mermaid::
   :alt: Namespace status transitions. A namespace starts at unknown and moves
         to ok, or to unstable, failing and failed while resources are
         unhealthy, or to the one-way stale, cancelled and superseded statuses
         that the action controller deletes.

   stateDiagram-v2
       direction LR
       [*] --> unknown: adopted by the<br/>collect controller

       unknown --> ok: nothing failing
       unknown --> unstable: something failing
       ok --> unstable: something failing

       state "degrading, one step per check" as degrading {
           direction LR
           unstable --> failing: still failing after<br/>settling_period
           failing --> failed: still failing after<br/>grace_period
       }

       degrading --> ok: nothing failing

       state one_way <<choice>>
       unknown --> one_way
       ok --> one_way
       degrading --> one_way

       one_way --> stale: older than ttl
       one_way --> cancelled: originating pipeline<br/>cancelled or gone
       one_way --> superseded: newer deployment of<br/>the same CI identity

       state "deleted by the action controller" as deleted
       failed --> deleted
       stale --> deleted
       cancelled --> deleted
       superseded --> deleted
       deleted --> [*]

       classDef initial fill:#eef2f6,stroke:#8b98a5,color:#1c2b36;
       classDef healthy fill:#eaf7ea,stroke:#2da44e,color:#0f3d1f,font-weight:bold;
       classDef unhealthy fill:#fff4e5,stroke:#d97706,color:#7a3e00;
       classDef terminal fill:#fde8ef,stroke:#cf222e,color:#5c0011;

       class unknown initial
       class ok healthy
       class unstable,failing unhealthy
       class stale,failed,cancelled,superseded terminal

Every check evaluates the namespace in a fixed order, and the first condition
that applies wins:

#. **Terminal statuses stick.** A namespace already marked ``cancelled`` or
   ``superseded`` keeps that status; it is waiting to be deleted.
#. **Cancelled.** With the ``cancelled`` check enabled, the originating GitLab
   pipeline is looked up from the ``cicd.skao.int/projectId`` and
   ``cicd.skao.int/pipelineId`` labels. If GitLab reports the pipeline as
   cancelled, or no longer knows about it, the namespace becomes ``cancelled``.
#. **Stale.** If the matcher defines a TTL and the namespace's
   ``creationTimestamp`` is at least that old, it becomes ``stale``. TTL is
   absolute age, not time since the last status change.
#. **Health.** Otherwise the namespace's health decides the status.

Health is assessed from Prometheus alerts when Prometheus is enabled: alerts
are fetched from ``/api/v1/alerts``, filtered to those whose ``namespace``
label matches (and whose ``datacentre`` label matches, when a datacentre is
configured), and whitelisted alert names are ignored unless their severity is
``critical``. When Prometheus is disabled, the collector falls back to the
Kubernetes API and treats any Deployment, StatefulSet or ReplicaSet with fewer
available replicas than desired as failing.

If nothing is failing, the namespace is ``ok``. If something is failing, the
status advances one step at a time, on successive checks:

* ``ok`` or ``unknown`` becomes ``unstable`` immediately;
* ``unstable`` becomes ``failing`` once the ``settling_period`` has elapsed
  since the status last changed;
* ``failing`` becomes ``failed`` once the ``grace_period`` has elapsed.

Recovery is immediate and needs no waiting period: as soon as a check finds
nothing failing, the namespace goes back to ``ok`` from any of ``unstable``,
``failing`` or ``failed``. Only ``stale``, ``cancelled`` and ``superseded``
are one-way — they exist to be acted on.

Each status change also records ``status_timestamp``, and — for ``ok``,
``unstable`` and ``failing`` — ``status_finalize_at`` and
``status_timeframe``, which are the "you have until…" values quoted in the
Slack notification. Changing status clears the notification bookkeeping so the
owner is told about the new status.

Superseded deployments
----------------------

The ``superseded`` check is the only one that compares namespaces with each
other, so it runs in the leader rather than in the per-namespace threads. Live
managed namespaces are grouped by CI identity — project plus merge request (or
project plus branch when there is no merge request), plus the job name — and
within a group they are bucketed by ``cicd.skao.int/jobId``. If a group holds
more than one deployment, every namespace outside the newest one is marked
``superseded`` with a five second finalisation window, so the older
environments for a re-run pipeline disappear promptly.

Namespaces missing the labels the identity is built from are skipped, which
means a namespace created outside the SKAO CI templates is never marked
superseded.

How work is spread across replicas
----------------------------------

The collect controller runs as a StatefulSet with more than one replica, and
each replica checks only its share of the namespaces. The assignment is a plain
hash: ``sha256(namespace name) % number of replicas``. Replica names come from
the StatefulSet's ``spec.replicas`` (``<statefulset>-0``, ``-1``, …), falling
back to live pod discovery by component label and service account if the
StatefulSet cannot be read. Because the hash is stable, a namespace stays with
the same replica across checks, and a scale change reshuffles deterministically.

Each replica keeps one thread per assigned namespace, created and torn down by
a reconciliation loop, and the thread's period comes from the matcher's
``check-namespace`` schedule. That same loop touches the heartbeat file the
liveness probe checks, so a replica whose reconciliation loop is wedged is
restarted by Kubernetes.

Three responsibilities are cluster-wide rather than per-replica — adopting new
namespaces, the superseded comparison, and cleaning up metrics files — so they
run in the leader only.

Leader election without a database
----------------------------------

Leader election is a file lock on a shared ``ReadWriteMany`` volume. The lock file is held with ``flock``; the holder renews
its lease by touching the file at half the lease TTL. A replica that finds the
lock held checks the file's access time, and if it is older than twice the
lease TTL it treats the lease as abandoned, removes the lock and takes over —
which is what prevents a crashed leader from deadlocking the deployment. On a
clean shutdown the lock is released explicitly.

The chart enables leader election only when a component runs more than one
replica; with a single replica the process always considers itself the leader
and no volume is mounted.

Leadership only actually gates work in the collect controller. The action
controller elects a leader but runs its delete and notify loops on every
replica, which is why the chart keeps it at a single replica.

Metrics without a scrape endpoint per pod
-----------------------------------------

The controllers do not expose an HTTP port. Each process instead writes its own
metrics to ``<pod name>.prom`` in a shared metrics volume, and the API merges
every ``*.prom`` file it finds into one Prometheus response at
``/api/metrics``. Prometheus therefore scrapes a single, stable endpoint no
matter how many controller replicas exist, and metrics survive a pod restart
because they are re-loaded from the file on startup.

The cost of that design is a shared ``ReadWriteMany`` volume and some
housekeeping: the collect controller's leader periodically deletes ``.prom``
files that do not belong to a live namespace-manager pod, so scaling down does
not leave phantom series behind.

Telling owners what happened
----------------------------

The action controller notifies through Slack, using the address in the
namespace's ``cicd.skao.int/notificationAddress`` annotation — put there by the
CI templates, resolved from the SKAO People Database through this project's own
``/api/people`` endpoint. A namespace with no notification address is acted on
silently.

Notifications are rendered from Jinja templates, one per status, and each
namespace is notified once per status: the ``notified_timestamp`` annotation is
the guard, and it is cleared whenever the status changes. Only ``unstable``,
``failing``, ``cancelled`` and ``superseded`` produce status notifications;
deletions produce their own message when the matcher asks for it.
