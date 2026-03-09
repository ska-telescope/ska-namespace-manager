# AGENTS.md

This document gives guidance to coding agents and contributors working in this repository.

## Shared Instructions

These rules are intended to be shared across SKAO Python repositories unless a project-specific section explicitly overrides them.

### Python version

- Use **Python 3.10**.

### Repository setup

- This repository uses a **git submodule** that contains project-wide tooling and standards.
- Always initialize and update submodules before working:


```bash
git submodule update --init --recursive
```

### Formatting, linting, and tests

- Formatting, linting, and tests are provided through the repository `Makefile`.
- Use the following commands:

```bash
make python-format
make python-lint
make python-test
```

- After making changes, always run:
  1. formatting
  2. linting
  3. tests

- If linting fails, fix the linting issues rather than bypassing them.

### Linting policy

- Do **not** add `# pylint: disable` comments to code sections unless you have formally asked first.
- These comments can hide genuine design issues and should be treated as an exception, not a convenience.

### Dependency maintenance

- During dedicated maintenance work, review dependencies on a sensible cadence, approximately weekly.
- Update to the latest compatible versions that do not require substantial refactoring.
- If an upgrade would require significant code changes, migration work, or behavior changes, ask before proceeding.

### Code styling

- Comment every module/class/function with `"""..."""` (no args/returns sections).
- For classes with substantial business logic or orchestration responsibilities, write a high-signal class docstring that explains the class role, the major responsibilities, and the important runtime invariants.
- In those logic-heavy classes, document important private/internal fields close to where they are initialized so a reader can immediately understand their purpose.
- No blank line after function/module docstrings.
- Newline after `if/for` blocks and before `return`/`yield`, except `if ...: return` single-line block style where return stays immediately inside block.
- Keep functions ordered by usage in larger files.
- Class method order: `__init__`, `@property`, `@staticmethod/@classmethod`, private methods, then public methods by ORDER of usage (ie, function that uses other functions should be last)
- Keep functions ordered by usage in larger files.

### Change boundaries

- Prefer small, reviewable changes over broad rewrites.
- Preserve public APIs and external behavior unless explicitly asked to change them.
- Ask before changing CI, packaging, release configuration, config schemas, or persisted data formats.
- Ask before introducing new dependencies, concurrency, caching, or background-processing patterns.

### Testing expectations

- Add or update tests for any behavior change.
- For bug fixes, add a regression test where practical.
- Do not delete or weaken tests simply to make the test suite pass without asking first.
- Keep Python 3.10 compatibility in both code and tests.
- Avoid patching code in an effort to increase code coverage if that produceces meanigless tests.

### Documentation, logging, and safety

- Update docstrings and relevant documentation when behavior changes.
- Prefer clear, actionable exceptions and meaningful log messages.
- Never commit secrets, tokens, credentials, or private keys.
- Do not log sensitive configuration values or secret material.

### Refactors and larger changes

- Before any **big changes**, ask the user to **commit any uncommitted work first**.
- After any **large change**, do a review pass over the codebase for :
  - naming consistency
  - code structure
  - module and package organization
  - general maintainability
  - documentation

### Configuration models

- For configuration, always use **typed objects** based on `BaseModel`.
- Avoid untyped configuration dictionaries where a structured model is appropriate.

### Expected working pattern

When making code changes, agents should generally follow this sequence:

1. Update submodules if needed.
2. Make the requested change following **change boundaries**, **testing expectations** and **documentation, logging, and safety**
3. Run formatting.
4. Run linting and fix issues.
5. Run tests.
6. For larger changes, do an additional review pass for consistency, structure and documentation.

---

## Project-Specific Instructions

### Purpose

- This service manages Kubernetes namespaces used by CI/CD workloads. It applies lifecycle policies, tracks namespace health with sharded collect-controller replicas, and deletes stale or failed namespaces through the leader action controller.
- There are three runtime surfaces:
  - `src/api.py`: FastAPI service for health, metrics, and People API-backed ownership lookups.
  - `src/collect_controller.py`: multi-replica sharded controller that collects ownership and health data in-process.
  - `src/action_controller.py`: leader-elected controller that deletes stale/failed namespaces and sends Slack notifications for `failing`, `unstable`, and delete events.
- The repo also ships the Helm chart under `charts/ska-ser-namespace-manager` and expects the application to run in Kubernetes. Prefer preserving deployment behavior and config shape unless asked otherwise.

### Architecture notes

- Main package code lives under `src/ska_ser_namespace_manager/` and is split into `api/`, `collector/`, `controller/`, `core/`, and `metrics/`.
- Controllers inherit from `Controller`/`LeaderController`, which combine Kubernetes access, thread management, config loading, and optional file-lock leader election. Preserve that layering when adding behavior.
- Namespace selection is matcher-driven. `NamespaceMatcher` supports `names`, `any`, and `all`, with precedence `all > any > names`. Reuse `match_namespace()` instead of adding ad hoc matching logic.
- Namespace lifecycle state is annotation-driven. The annotation keys in `core/types.py` are part of the operational contract with collectors, controllers, templates, and chart manifests. Do not rename them casually.
- Notification behavior is rendered from Jinja templates in `src/ska_ser_namespace_manager/resources/templates/`. When changing Slack message content, update the templates rather than hardcoding strings in controllers.
- Config is loaded through typed Pydantic models via `ConfigLoader`. Keep new config in typed models and preserve compatibility with the YAML structure consumed by the Helm chart values and rendered secrets/config maps.

### Local conventions

- Keep changes Python 3.10 and Pydantic v2 compatible. This repo uses `model_post_init()` and `model_dump_json()` patterns already present in the codebase.
- Entrypoint scripts at `src/*.py` are thin wrappers. Put business logic in package modules under `src/ska_ser_namespace_manager/`, not in the top-level scripts.
- Use the existing `core.logging.logging` logger and current exception-handling style for controller/API code. Prefer actionable logs that include namespace names, actions, and status values.
- Preserve the current namespace status vocabulary: `ok`, `stale`, `failing`, `failed`, `unstable`, `unknown`.
- Be careful with ownership and notification flows. Slack addresses are encoded/decoded through `core.utils`, and notification content comes from Jinja templates plus `Notifier`.
- `FORBIDDEN_NAMESPACES` and the controller’s own namespace are intentionally excluded from management. Do not broaden namespace selection without checking those safeguards.

### Dependency constraints

- This project already depends on FastAPI, Kubernetes Python client, Slack Bolt, Jinja2, and SKAO internal APIs. Ask before introducing new third-party dependencies.
- `ska-cicd-services-api` is pinned exactly to `0.31.0`. Treat SKAO internal dependency changes as potentially breaking and verify them carefully before updating.
- The Docker image and CI pipeline assume Poetry-managed dependencies and the current package layout under `src/`. Avoid packaging changes unless explicitly requested.
- There is a strong repository convention that configuration models are typed `BaseModel` classes. Do not introduce raw dict-based config plumbing where a model should exist.

### Testing notes

- Unit tests are the meaningful local safety net. `make python-test` is configured to run `./tests/unit`.
- For logic changes in controllers, matchers, config loading, notifier behavior, or Kubernetes wrappers, add or update unit tests near the touched module.
- When changing chart values, templates, or runtime config shape, also review whether tests need to assert the new config contract even if there is no full chart test suite.

### Release or CI notes

- CI is GitLab-based via `.gitlab-ci.yml` and shared SKAO template includes for Python, Helm chart, OCI image, Kubernetes test runner, docs, release, and finaliser stages.
- The pipeline uses recursive submodules, so repository tooling in `.make/` is expected to come from the shared submodule setup.
- The Helm chart under `charts/ska-ser-namespace-manager/` is part of the deliverable. Changes to config models, ports, probes, secret shapes, or entrypoints usually require a matching chart review.
- The container image defaults to running `python3 -u /opt/ska_ser_namespace_manager/api.py`. If you change runtime entrypoints or file locations, update the Dockerfile and chart manifests together.
