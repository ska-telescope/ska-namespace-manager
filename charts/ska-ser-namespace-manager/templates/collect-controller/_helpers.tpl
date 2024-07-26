{{- define "ska-ser-namespace-manager.collect-controller.name" -}}
{{ template "ska-ser-namespace-manager.name" . }}-collect-controller
{{- end -}}

{{- define "ska-ser-namespace-manager.collect-controller.labels" -}}
{{- template "ska-ser-namespace-manager.labels.merge" (list
  (include "ska-ser-namespace-manager.labels.common" .)
  (include "ska-ser-namespace-manager.collect-controller.matchLabels" .)
) -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.collect-controller.matchLabels" -}}
{{- template "ska-ser-namespace-manager.labels.merge" (list
  (include "ska-ser-namespace-manager.matchLabels.common" .)
  (include "ska-ser-namespace-manager.labels.component" "collect-controller")
) -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.collect-controller.configName" -}}
{{- printf "%s-collect-controller-config" (include "ska-ser-namespace-manager.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.collect-controller.leaderElectionVol" -}}
{{- printf "%s-collect-controller-leader" (include "ska-ser-namespace-manager.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.collect-controller.config" -}}
{{- template "ska-ser-namespace-manager.merge" (list
  (toYaml .Values.config)
  (toYaml .Values.collectController.config)
  (toYaml (dict "leader_election" (dict "enabled" (gt (int .Values.collectController.replicas) 1))) )
) -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.collect-controller.configPath" -}}
{{- coalesce .Values.collectController.configPath .Values.configPath -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.collect-controller.leaderElectionPath" -}}
{{- coalesce .Values.collectController.config.leader_election.path .Values.leaderElectionPath -}}
{{- end -}}
