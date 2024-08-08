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
{{- printf "%s-collect-ctl-config" (include "ska-ser-namespace-manager.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.collect-controller.serviceAccount" -}}
{{- printf "%s-collect-ctl-sa" (include "ska-ser-namespace-manager.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.collect-controller.clusterWidePrefix" -}}
{{- printf "%s-%s-collect-ctl" (include "ska-ser-namespace-manager.fullname" .) (.Release.Namespace | sha256sum | substr 0 4) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.collect-controller.leaderElectionVol" -}}
{{- printf "%s-collect-ctl-leader" (include "ska-ser-namespace-manager.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.collect-controller.config" -}}
{{- template "ska-ser-namespace-manager.merge" (list
  (toYaml .Values.config)
  (toYaml .Values.collectController.config)
  (include "ska-ser-namespace-manager.collect-controller.contextConfig" .)
) -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.collect-controller.configVersion" -}}
{{ include "ska-ser-namespace-manager.collect-controller.config" . | sha256sum | substr 0 16 }}
{{- end -}}

{{- define "ska-ser-namespace-manager.collect-controller.contextConfig" -}}
leader_election:
  enabled: {{ gt (int .Values.collectController.replicas) 1 }}
context:
  namespace: {{ .Release.Namespace }}
  service_account: {{ template "ska-ser-namespace-manager.collect-controller.serviceAccount" . }}
  config_secret: {{ template "ska-ser-namespace-manager.collect-controller.configName" . }}
  config_path: {{ template "ska-ser-namespace-manager.collect-controller.configPath" . }}
  image: {{ include "ska-ser-namespace-manager.image" (list . .Values.collectController) }}
people_api:
{{- if .Values.api.service.https.enabled }}
  url: https://{{ include "ska-ser-namespace-manager.api.serviceName" . }}.{{ .Release.Namespace }}.svc:{{ .Values.api.service.https.port }}
{{- else }}
  url: http://{{ include "ska-ser-namespace-manager.api.serviceName" . }}.{{ .Release.Namespace }}.svc:{{ .Values.api.service.http.port }}
{{- end }}
{{- end -}}

{{- define "ska-ser-namespace-manager.collect-controller.configPath" -}}
{{- coalesce .Values.collectController.configPath .Values.configPath -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.collect-controller.leaderElectionPath" -}}
{{- coalesce .Values.collectController.config.leader_election.path .Values.leaderElectionPath -}}
{{- end -}}
