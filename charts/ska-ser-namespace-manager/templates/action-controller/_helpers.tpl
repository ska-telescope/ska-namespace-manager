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
{{- printf "%s-action-ctl-config" (include "ska-ser-namespace-manager.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.action-controller.serviceAccount" -}}
{{- printf "%s-action-ctl-sa" (include "ska-ser-namespace-manager.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.action-controller.clusterWidePrefix" -}}
{{- printf "%s-%s-action-ctl" (include "ska-ser-namespace-manager.fullname" .) (.Release.Namespace | sha256sum | substr 0 4) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.action-controller.leaderElectionVol" -}}
{{- printf "%s-action-ctl-leader" (include "ska-ser-namespace-manager.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.action-controller.config" -}}
{{- template "ska-ser-namespace-manager.merge" (list
  (toYaml .Values.config)
  (toYaml .Values.actionController.config)
  (include "ska-ser-namespace-manager.action-controller.contextConfig" .)
) -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.action-controller.configVersion" -}}
{{ include "ska-ser-namespace-manager.action-controller.config" . | sha256sum | substr 0 16 }}
{{- end -}}

{{- define "ska-ser-namespace-manager.action-controller.contextConfig" -}}
leader_election:
  enabled: {{ gt (int .Values.actionController.replicas) 1 }}
context:
  namespace: {{ .Release.Namespace }}
  service_account: {{ include "ska-ser-namespace-manager.action-controller.serviceAccount" . }}
  matchLabels:
    {{ include "ska-ser-namespace-manager.action-controller.matchLabels" . | nindent 4 }}
{{- end -}}

{{- define "ska-ser-namespace-manager.action-controller.configPath" -}}
{{- coalesce .Values.actionController.configPath .Values.configPath -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.action-controller.leaderElectionPath" -}}
{{- coalesce .Values.actionController.config.leader_election.path .Values.leaderElectionPath -}}
{{- end -}}
