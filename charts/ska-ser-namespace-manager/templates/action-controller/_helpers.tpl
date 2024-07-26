{{- define "ska-ser-namespace-manager.action-controller.name" -}}
{{ template "ska-ser-namespace-manager.name" . }}-action-controller
{{- end -}}

{{- define "ska-ser-namespace-manager.action-controller.labels" -}}
{{- template "ska-ser-namespace-manager.labels.merge" (list
  (include "ska-ser-namespace-manager.labels.common" .)
  (include "ska-ser-namespace-manager.action-controller.matchLabels" .)
) -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.action-controller.matchLabels" -}}
{{- template "ska-ser-namespace-manager.labels.merge" (list
  (include "ska-ser-namespace-manager.matchLabels.common" .)
  (include "ska-ser-namespace-manager.labels.component" "action-controller")
) -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.action-controller.configName" -}}
{{- printf "%s-action-controller-config" (include "ska-ser-namespace-manager.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.action-controller.leaderElectionVol" -}}
{{- printf "%s-action-controller-leader" (include "ska-ser-namespace-manager.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.action-controller.config" -}}
{{- template "ska-ser-namespace-manager.merge" (list
  (toYaml .Values.config)
  (toYaml .Values.actionController.config)
  (toYaml (dict "leader_election_enabled" (gt (int .Values.actionController.replicas) 1) ))
) -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.action-controller.configPath" -}}
{{- coalesce .Values.actionController.configPath .Values.configPath -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.action-controller.leaderElectionPath" -}}
{{- coalesce .Values.actionController.config.leader_election.path .Values.leaderElectionPath -}}
{{- end -}}
