#!/usr/bin/env bash

set -euo pipefail

COUNT="${COUNT:-20}"
PREFIX="${PREFIX:-ci-load-test-}"
SAMPLE_COUNT="${SAMPLE_COUNT:-120}"
SAMPLE_INTERVAL_SECONDS="${SAMPLE_INTERVAL_SECONDS:-3}"
NSM_NAMESPACE="${NSM_NAMESPACE:-ska-ser-namespace-manager}"

TMPDIR_PATH="$(mktemp -d)"
RESOURCE_SAMPLES="${TMPDIR_PATH}/resource-samples.tsv"
CREATED_ANY="false"
WATCH_PID=""
SAMPLE_PID=""

cleanup_tmpdir() {
  rm -rf "${TMPDIR_PATH}"
}

count_matching_namespaces() {
  local count

  count="$(
    kubectl get namespaces --no-headers 2>/dev/null \
      | grep "^${PREFIX}" \
      | wc -l \
      | tr -d ' '
  )"

  echo "${count}"
}

capture_resource_sample() {
  local top_output
  local totals
  local pod_count

  pod_count="$(
    kubectl get pods -n "${NSM_NAMESPACE}" --no-headers 2>/dev/null \
      | wc -l \
      | tr -d ' '
  )"

  if ! top_output="$(kubectl top pod -n "${NSM_NAMESPACE}" --no-headers 2>/dev/null)"; then
    top_output=""
  fi

  totals="$(
    printf '%s\n' "${top_output}" | awk '
      {
        cpu_value = $2
        mem_value = $3

        if (cpu_value ~ /m$/) {
          sub(/m$/, "", cpu_value)
          cpu_m += cpu_value
        }

        if (mem_value ~ /Mi$/) {
          sub(/Mi$/, "", mem_value)
          mem_mi += mem_value
        } else if (mem_value ~ /Gi$/) {
          sub(/Gi$/, "", mem_value)
          mem_mi += mem_value * 1024
        } else if (mem_value ~ /Ki$/) {
          sub(/Ki$/, "", mem_value)
          mem_mi += mem_value / 1024
        }
      }
      END {
        printf "%.3f\t%.3f\n", cpu_m, mem_mi
      }
    '
  )"

  printf '%s\t%s\n' "${totals}" "${pod_count}"
}

sample_namespace_resources() {
  local sample_index=0

  : > "${RESOURCE_SAMPLES}"

  while [ "${sample_index}" -lt "${SAMPLE_COUNT}" ]; do
    local sample

    if sample="$(capture_resource_sample)"; then
      printf '%s\n' "${sample}" >> "${RESOURCE_SAMPLES}"
    fi

    sample_index=$((sample_index + 1))

    if [ "${sample_index}" -lt "${SAMPLE_COUNT}" ]; then
      sleep "${SAMPLE_INTERVAL_SECONDS}"
    fi
  done
}

print_average_resources() {
  if [ ! -s "${RESOURCE_SAMPLES}" ]; then
    echo "No pod resource samples were collected from namespace '${NSM_NAMESPACE}'." >&2
    exit 1
  fi

  awk -F '\t' '
    {
      cpu_sum += $1
      mem_sum += $2
      pod_sum += $3
      samples += 1
    }
    END {
      if (samples == 0) {
        exit 1
      }
      avg_cpu = cpu_sum / samples
      avg_mem = mem_sum / samples
      printf "Samples: %d\n", samples
      printf "Accumulated Pods: %.0f\n", pod_sum
      printf "Average CPU: %.3fm (%.3f cores)\n", avg_cpu, avg_cpu / 1000
      printf "Average Memory: %.3fMi (%.3f Gi)\n", avg_mem, avg_mem / 1024
    }
  ' "${RESOURCE_SAMPLES}"
}

print_current_resources() {
  local sample

  if ! sample="$(capture_resource_sample)"; then
    echo "Namespace CPU: unavailable"
    echo "Namespace Memory: unavailable"
    return
  fi

  printf '%s\n' "${sample}" | awk -F '\t' '
    {
      printf "Namespace Pods: %d\n", $3
      printf "Namespace CPU: %.3fm (%.3f cores)\n", $1, $1 / 1000
      printf "Namespace Memory: %.3fMi (%.3f Gi)\n", $2, $2 / 1024
    }
  '
}

cleanup() {
  if [ -n "${WATCH_PID}" ]; then
    kill "${WATCH_PID}" 2>/dev/null || true
    wait "${WATCH_PID}" 2>/dev/null || true
    WATCH_PID=""
  fi

  if [ -n "${SAMPLE_PID}" ]; then
    kill "${SAMPLE_PID}" 2>/dev/null || true
    wait "${SAMPLE_PID}" 2>/dev/null || true
    SAMPLE_PID=""
  fi

  if [ "${CREATED_ANY}" = "true" ]; then
    echo
    echo "Deleting ${COUNT} namespaces with prefix '${PREFIX}'..."
    for i in $(seq 1 "${COUNT}"); do
      kubectl delete namespace "${PREFIX}${i}" --ignore-not-found=true >/dev/null
    done
  fi

  cleanup_tmpdir
}

trap cleanup EXIT

if [ "$(count_matching_namespaces)" != "0" ]; then
  echo "Found existing namespaces with prefix '${PREFIX}'." >&2
  echo "Refusing to continue because the baseline would be invalid." >&2
  exit 1
fi

echo "Creating ${COUNT} namespaces with prefix '${PREFIX}'..."
for i in $(seq 1 "${COUNT}"); do
  kubectl create namespace "${PREFIX}${i}" >/dev/null
done
CREATED_ANY="true"

echo "Monitoring namespace-manager load for ${SAMPLE_COUNT} samples every ${SAMPLE_INTERVAL_SECONDS} second(s)..."
sample_namespace_resources &
SAMPLE_PID=$!
watch -n 1 -t "
date
echo
echo \"Namespaces: \$(kubectl get namespaces --no-headers 2>/dev/null | grep '^${PREFIX}' | wc -l | tr -d ' ')\"
echo \"CronJobs:   \$(kubectl -n '${NSM_NAMESPACE}' get cronjobs --no-headers 2>/dev/null | wc -l | tr -d ' ')\"
echo \"Jobs:       \$(kubectl -n '${NSM_NAMESPACE}' get jobs --no-headers 2>/dev/null | wc -l | tr -d ' ')\"
echo \"Pods:       \$(kubectl -n '${NSM_NAMESPACE}' get pods --no-headers 2>/dev/null | wc -l | tr -d ' ')\"
echo
$(typeset -f capture_resource_sample)
$(typeset -f print_current_resources)
print_current_resources
echo
kubectl get --raw /metrics \
  | grep '^apiserver_request_total' \
  | grep -E 'resource=\"(cronjobs|jobs|pods|namespaces)\"' \
  | grep -E 'verb=\"(LIST|GET|CREATE|PATCH|DELETE)\"' \
  | sort || true
" &
WATCH_PID=$!
wait "${SAMPLE_PID}" 2>/dev/null || true
SAMPLE_PID=""
kill "${WATCH_PID}" 2>/dev/null || true
wait "${WATCH_PID}" 2>/dev/null || true
WATCH_PID=""

echo
echo "Average namespace-manager resource usage during monitoring:"
print_average_resources
