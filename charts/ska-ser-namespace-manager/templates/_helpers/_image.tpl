{{- define "ska-ser-namespace-manager.image" -}}
{{- $ := index . 0 }}
{{- $app := index . 1 }}
{{- $tag := coalesce $app.image.tag $.Values.image.tag (include "ska-ser-namespace-manager.appVersion" $) -}}
{{- $repository := coalesce $app.image.repository $.Values.image.repository -}}
{{- printf "%s:%s" $repository $tag  -}}
{{- end -}}
