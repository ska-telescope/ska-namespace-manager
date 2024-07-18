{{- define "ska-ser-namespace-manager.merge" -}}
{{- $merged := dict -}}
{{- range . -}}
  {{- $merged = mergeOverwrite $merged (fromYaml .) -}}
{{- end -}}
{{- with $merged -}}
  {{- toYaml $merged -}}
{{- end -}}
{{- end -}}