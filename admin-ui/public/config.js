// Default runtime config baked into the image. Intentionally sets NO apiBaseUrl
// so VM/docker-compose and local dev fall back to the build-time VITE_API_URL.
// On Kubernetes this file is replaced by a ConfigMap mount (admin-ui-config)
// that sets apiBaseUrl from the chart's ingress host — see
// deploy/helm/niyan/templates/admin-ui-config.yaml.
window.__NIYAN_CONFIG__ = {};
