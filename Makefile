PROJECT = ska-namespace-manager
HELM_RELEASE ?= ska-namespace-manager

include .make/base.mk
include .make/oci.mk
include .make/k8s.mk
include .make/python.mk
include .make/helm.mk

-include PrivateRules.mak
