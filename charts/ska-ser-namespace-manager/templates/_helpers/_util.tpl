{{- define "ska-ser-namespace-manager.merge" -}}
{{- $merged := dict -}}
{{- range . -}}
  {{- $merged = mergeOverwrite $merged (fromYaml .) -}}
{{- end -}}
{{- with $merged -}}
  {{- toYaml $merged -}}
{{- end -}}
{{- end -}}

{{/*
Render an arbitrary value (string or object) through `tpl` so consumers can use
template helpers inside `.Values.extraDeploy` entries.
*/}}
{{- define "ska-ser-namespace-manager.render" -}}
{{- $ctx := .context -}}
{{- if kindIs "string" .value -}}
{{- tpl .value $ctx -}}
{{- else -}}
{{- tpl (toYaml .value) $ctx -}}
{{- end -}}
{{- end -}}
