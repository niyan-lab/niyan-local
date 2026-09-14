/**
 * Dev proxy: browser → /api-proxy/... → header X-Api-Base target.
 */
import type { Plugin } from "vite";
import http from "node:http";
import https from "node:https";
import { URL } from "node:url";

export function apiProxy(): Plugin {
  return {
    name: "api-proxy",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        if (!req.url?.startsWith("/api-proxy")) return next();

        const base = (req.headers["x-api-base"] as string | undefined)?.replace(/\/$/, "");
        if (!base) {
          res.statusCode = 400;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({ error: "Missing API base URL in Settings." }));
          return;
        }

        let target: URL;
        try {
          const path = req.url.replace(/^\/api-proxy/, "") || "/";
          target = new URL(path, base.endsWith("/") ? base : `${base}/`);
        } catch {
          res.statusCode = 400;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({ error: "Invalid API base URL" }));
          return;
        }

        const lib = target.protocol === "https:" ? https : http;
        const headers: Record<string, string | string[] | undefined> = { ...req.headers };
        delete headers.host;
        delete headers["x-api-base"];
        headers.host = target.host;

        const upstream = lib.request(
          target,
          { method: req.method, headers },
          (up) => {
            res.statusCode = up.statusCode || 502;
            for (const [k, v] of Object.entries(up.headers)) {
              if (v != null && k.toLowerCase() !== "transfer-encoding") {
                res.setHeader(k, v);
              }
            }
            up.pipe(res);
          }
        );
        upstream.on("error", (err) => {
          res.statusCode = 502;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({ error: `Cannot reach API: ${err.message}` }));
        });
        req.pipe(upstream);
      });
    },
  };
}
