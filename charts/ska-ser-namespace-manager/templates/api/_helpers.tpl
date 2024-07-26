{{- define "ska-ser-namespace-manager.api.name" -}}
{{ template "ska-ser-namespace-manager.name" . }}-api
{{- end -}}

{{- define "ska-ser-namespace-manager.api.labels" -}}
{{- template "ska-ser-namespace-manager.labels.merge" (list
  (include "ska-ser-namespace-manager.labels.common" .)
  (include "ska-ser-namespace-manager.api.matchLabels" .)
) -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.api.matchLabels" -}}
{{- template "ska-ser-namespace-manager.labels.merge" (list
  (include "ska-ser-namespace-manager.matchLabels.common" .)
  (include "ska-ser-namespace-manager.labels.component" "api")
) -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.api.serviceName" -}}
{{- printf "%s-api-svc" (include "ska-ser-namespace-manager.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.api.configName" -}}
{{- printf "%s-api-config" (include "ska-ser-namespace-manager.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.api.config" -}}
{{- template "ska-ser-namespace-manager.merge" (list
  (toYaml .Values.config)
  (toYaml .Values.api.config)
  (toYaml (dict "https_enabled" .Values.api.service.https.enabled))
) -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.api.configPath" -}}
{{- coalesce .Values.api.configPath .Values.configPath -}}
{{- end -}}
