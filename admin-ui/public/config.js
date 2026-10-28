// Same-origin console. apiBaseUrl "" makes the browser call /api on whatever
// host opened this page; nginx proxies that to niyan-api. Replace this file
// only when the API is served from a different host.
window.__NIYAN_CONFIG__ = { apiBaseUrl: "" };
