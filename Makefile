PROJECT = ska-ser-namespace-manager
HELM_RELEASE ?= ska-ser-namespace-manager

include .make/base.mk
include .make/oci.mk
include .make/k8s.mk
include .make/python.mk
include .make/helm.mk

-include PrivateRules.mak

CHART_ENVIRONMENTS_DIR = ./charts/$(K8S_CHART)/environments

ALL_VALUES_EXISTS := $(shell if [ -f "$(CHART_ENVIRONMENTS_DIR)/all.yml" ]; then echo true; else echo false; fi)
ifeq ($(ALL_VALUES_EXISTS),true)
K8S_CHART_PARAMS += -f <(envsubst < $(CHART_ENVIRONMENTS_DIR)/all.yml)
endif

ENVIRONMENT ?= # environment to deploy to, matching files under charts/ska-ser-namespace-manager/environments

ENVIRONMENT_VALUES_EXISTS := $(shell if [ -f "$(CHART_ENVIRONMENTS_DIR)/$(ENVIRONMENT).yml" ]; then echo true; else echo false; fi)
ifeq ($(ENVIRONMENT_VALUES_EXISTS),true)
K8S_CHART_PARAMS += -f <(envsubst < $(CHART_ENVIRONMENTS_DIR)/$(ENVIRONMENT).yml)
endif

ifeq ($(ENVIRONMENT),ci)
K8S_CHART_PARAMS += --set image.tag=$(VERSION)-dev.c$(CI_COMMIT_SHORT_SHA)
endif

# K8S_EXTRA_VALUES: space-separated list of additional helm values files,
# each piped through envsubst (same as all.yml / $(ENVIRONMENT).yml).
# Later entries override earlier ones, and the list is appended after the
# environment files so it always wins.
K8S_EXTRA_VALUES ?=
K8S_CHART_PARAMS += $(foreach extra_values_file,$(K8S_EXTRA_VALUES),-f <(envsubst < $(extra_values_file)))

PYTHON_SWITCHES_FOR_PYLINT = \
	--disable "fixme,duplicate-code,arguments-differ" \
	--min-public-methods 0 \
	--max-attributes 10 \
	--max-positional-arguments 8 \
	--max-args 8
PYTHON_TEST_FILE = ./tests/unit
PYTHON_VARS_AFTER_PYTEST = --disable-warnings
K8S_TEST_TEST_COMMAND = $(PYTHON_VARS_BEFORE_PYTEST) $(PYTHON_RUNNER) \
	pytest --disable-warnings ./tests/integration -v -s --log-cli-level=INFO \
	| tee pytest.stdout
