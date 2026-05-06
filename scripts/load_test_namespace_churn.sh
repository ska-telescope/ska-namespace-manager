#!/usr/bin/env bash

set -euo pipefail

COUNT="${COUNT:-10}"
PREFIX="${PREFIX:-nstest-}"
SAMPLE_COUNT="${SAMPLE_COUNT:-5}"
SAMPLE_INTERVAL_SECONDS="${SAMPLE_INTERVAL_SECONDS:-3}"
NSM_NAMESPACE="${NSM_NAMESPACE:-ska-ser-namespace-manager}"
DELETE_NAMESPACES="${DELETE_NAMESPACES:-false}"

TMPDIR_PATH="$(mktemp -d)"
RESOURCE_SAMPLES="${TMPDIR_PATH}/resource-samples.tsv"
DEPLOYMENT_RESULTS="${TMPDIR_PATH}/deployment-results.log"
CREATED_ANY="false"
STOP_REQUESTED="false"

cleanup_tmpdir() {
  rm -rf "${TMPDIR_PATH}"
}

count_matching_namespaces() {
  local count

  count="$(
    kubectl get namespaces --no-headers 2>/dev/null \
      | awk -v prefix="${PREFIX}" '$1 ~ ("^" prefix) { count += 1 } END { print count + 0 }' \
      | tr -d ' '
  )"

  echo "${count}"
}

create_test_deployments() {
  local namespace="$1"
  local total_deployment_count
  local broken_deployment_count
  local healthy_deployment_count
  local workload_profile
  local deployment_message

  total_deployment_count="$((RANDOM % 5 + 1))"
  workload_profile="$((RANDOM % 3))"

  case "${workload_profile}" in
    0)
      healthy_deployment_count="${total_deployment_count}"
      broken_deployment_count=0
      ;;
    1)
      broken_deployment_count="${total_deployment_count}"
      healthy_deployment_count=0
      ;;
    *)
      if [ "${total_deployment_count}" -eq 1 ]; then
        healthy_deployment_count=1
        broken_deployment_count=0
      else
        broken_deployment_count="$((RANDOM % (total_deployment_count - 1) + 1))"
        healthy_deployment_count="$((total_deployment_count - broken_deployment_count))"
      fi
      ;;
  esac

  deployment_message="Creating ${healthy_deployment_count} healthy deployment(s) and ${broken_deployment_count} broken deployment(s) in namespace '${namespace}'..."
  echo "${deployment_message}"
  printf '%s\n' "${deployment_message}" >> "${DEPLOYMENT_RESULTS}"

  for deployment_index in $(seq 1 "${healthy_deployment_count}"); do
    local deployment_name="healthy-${deployment_index}"

    kubectl -n "${namespace}" create deployment "${deployment_name}" \
      --image=busybox:1.36 \
      -- /bin/sh -c 'sleep 3600' >/dev/null
  done

  for deployment_index in $(seq 1 "${broken_deployment_count}"); do
    local deployment_name="broken-${deployment_index}"

    kubectl -n "${namespace}" create deployment "${deployment_name}" \
      --image=busybox:1.36 \
      -- /bin/sh -c 'exit 1' >/dev/null
  done
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

  while [ "${sample_index}" -lt "${SAMPLE_COUNT}" ] && [ "${STOP_REQUESTED}" != "true" ]; do
    local sample

    if sample="$(capture_resource_sample)"; then
      printf '%s\n' "${sample}" >> "${RESOURCE_SAMPLES}"
    fi

    sample_index=$((sample_index + 1))

    print_monitor_snapshot "${sample_index}"

    if [ "${sample_index}" -lt "${SAMPLE_COUNT}" ] && [ "${STOP_REQUESTED}" != "true" ]; then
      sleep "${SAMPLE_INTERVAL_SECONDS}" || true
    fi
  done
}

print_average_resources() {
  if [ ! -s "${RESOURCE_SAMPLES}" ]; then
    echo "No pod resource samples were collected from namespace '${NSM_NAMESPACE}'." >&2
    return
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
    echo "Pod Resources: unavailable"
    return
  fi

  printf '%s\n' "${sample}" | awk -F '\t' '
    {
      printf "Namespace Pods: %d\n", $3
      printf "Namespace CPU: %.3fm (%.3f cores)\n", $1, $1 / 1000
      printf "Namespace Memory: %.3fMi (%.3f Gi)\n", $2, $2 / 1024
    }
  '

  print_pod_resources
}

print_deployment_results() {
  if [ ! -s "${DEPLOYMENT_RESULTS}" ]; then
    echo "Deployment Creation: none recorded"
    return
  fi

  echo "Deployment Creation:"
  cat "${DEPLOYMENT_RESULTS}"
}

print_pod_resources() {
  local pod_top_output

  if ! pod_top_output="$(kubectl top pod -n "${NSM_NAMESPACE}" 2>/dev/null)"; then
    echo "Pod Resources: unavailable"
    return
  fi

  if [ -z "${pod_top_output}" ]; then
    echo "Pod Resources: none"
    return
  fi

  echo "Pod Resources:"
  printf '%s\n' "${pod_top_output}"
}

print_monitor_snapshot() {
  local sample_index="$1"

  if [ -t 1 ]; then
    clear
  fi

  date
  echo
  echo "Sample ${sample_index}/${SAMPLE_COUNT}"
  echo "Namespaces: $(kubectl get namespaces --no-headers 2>/dev/null | awk -v prefix="${PREFIX}" '$1 ~ ("^" prefix) { count += 1 } END { print count + 0 }')"
  echo "CronJobs:   $(kubectl -n "${NSM_NAMESPACE}" get cronjobs --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  echo "Jobs:       $(kubectl -n "${NSM_NAMESPACE}" get jobs --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  echo "Pods:       $(kubectl -n "${NSM_NAMESPACE}" get pods --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  echo
  print_current_resources
}

handle_interrupt() {
  STOP_REQUESTED="true"
  echo
  echo "Stopping monitoring early and finalizing results..."
}

cleanup() {
  if [ "${CREATED_ANY}" = "true" ]; then
    if [ "${DELETE_NAMESPACES}" != "true" ]; then
      echo
      echo "Skipping namespace deletion because DELETE_NAMESPACES=${DELETE_NAMESPACES}."
      cleanup_tmpdir
      return
    fi

    echo
    echo "Deleting ${COUNT} namespaces with prefix '${PREFIX}'..."
    for i in $(seq 1 "${COUNT}"); do
      kubectl delete namespace "${PREFIX}${i}" --ignore-not-found=true --wait=false >/dev/null
    done
  fi

  cleanup_tmpdir
}

trap cleanup EXIT
trap handle_interrupt INT TERM

if [ "$(count_matching_namespaces)" != "0" ]; then
  echo "Found existing namespaces with prefix '${PREFIX}'." >&2
  echo "Refusing to continue because the baseline would be invalid." >&2
  exit 1
fi

echo "Creating ${COUNT} namespaces with prefix '${PREFIX}'..."
for i in $(seq 1 "${COUNT}"); do
  namespace_name="${PREFIX}${i}"

  kubectl create namespace "${namespace_name}" >/dev/null
  kubectl label namespace "${namespace_name}" "cicd.skao.int/author=j-pandeirada" --overwrite >/dev/null
  kubectl annotate namespace "${namespace_name}" "cicd.skao.int/authorEmail=joao.pandeirada@atlar.pt" --overwrite >/dev/null
  create_test_deployments "${namespace_name}"
done
CREATED_ANY="true"

echo "Monitoring namespace-manager load for ${SAMPLE_COUNT} samples every ${SAMPLE_INTERVAL_SECONDS} second(s)..."
sample_namespace_resources

#echo
#echo "Average namespace-manager resource usage during monitoring:"
#print_average_resources
echo
print_deployment_results
