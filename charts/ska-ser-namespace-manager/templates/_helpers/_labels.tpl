{{- define "ska-ser-namespace-manager.labels.merge" -}}
{{- $labels := dict -}}
{{- range . -}}
  {{- $labels = merge $labels (fromYaml .) -}}
{{- end -}}
{{- with $labels -}}
  {{- toYaml $labels -}}
{{- end -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.labels.helm" -}}
helm.sh/chart: {{ template "ska-ser-namespace-manager.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "ska-ser-namespace-manager.labels.version" -}}
app.kubernetes.io/version: {{ template "ska-ser-namespace-manager.chartVersion" . }}
{{- end -}}

{{- define "ska-ser-namespace-manager.labels.common" -}}
{{- template "ska-ser-namespace-manager.labels.merge" (list
  (include "ska-ser-namespace-manager.labels.helm" .)
  (include "ska-ser-namespace-manager.labels.version" .)
  (toYaml .Values.labels)
) -}}
{{- end -}}

{{- define "ska-ser-namespace-manager.matchLabels.common" -}}
app.kubernetes.io/part-of: {{ template "ska-ser-namespace-manager.fullname" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "ska-ser-namespace-manager.labels.component" -}}
app.kubernetes.io/component: {{ . }}
{{- end -}}

{{- define "ska-ser-namespace-manager.labels.componentVersion" -}}
app.kubernetes.io/componentVersion: {{ . }}
{{- end -}}

{{- define "ska-ser-namespace-manager.labels.name" -}}
app.kubernetes.io/name: {{ . }}
{{- end -}}
