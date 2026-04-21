import cookieParser from "cookie-parser";
import express, { Request, Response } from "express";
import fs from "node:fs";
import path from "node:path";
import helmet from "helmet";

import { createRouter } from "./routers";
import { AuthClient } from "./infrastructure/authClient";
import { getSettings } from "./infrastructure/config";
import { buildUpstreamClients } from "./infrastructure/httpClients";
import { SessionStore } from "./infrastructure/sessions";
import { TokenSecurity } from "./infrastructure/security";
import { WebService } from "./services";

export function createApp() {
  const settings = getSettings();

  const authClient = new AuthClient(settings);
  const tokenSecurity = new TokenSecurity(settings);
  const sessionStore = new SessionStore(settings.sessionTtlSeconds);
  const upstream = buildUpstreamClients(settings);
  const service = new WebService(settings, authClient, upstream, tokenSecurity, sessionStore);

  const app = express();
  const serviceRoot = path.resolve(__dirname, "..");
  const publicDir = path.join(serviceRoot, "dist", "public");

  app.use(
    helmet({
      contentSecurityPolicy: false,
    }),
  );
  app.use(express.json({ limit: "1mb" }));
  app.use(cookieParser(settings.cookieSecret));

  app.get("/health", (_req: Request, res: Response) => {
    res.status(200).json({ status: "ok" });
  });

  app.use("/api", createRouter(service, settings));

  if (fs.existsSync(publicDir)) {
    app.use(express.static(publicDir));
    app.get("*", (req: Request, res: Response) => {
      if (req.path.startsWith("/api") || req.path === "/health") {
        res.status(404).json({ detail: "Not found" });
        return;
      }
      res.sendFile(path.join(publicDir, "index.html"));
    });
  } else {
    app.get("/", (_req: Request, res: Response) => {
      res
        .status(200)
        .send("Web Service started, but frontend bundle is missing. Run npm run build to generate dist/public.");
    });
  }

  return { app, settings };
}

if (require.main === module) {
  const { app, settings } = createApp();

  console.info(
    "JWT TTL config: USER_ACCESS_TOKEN_TTL_MINUTES=%s, USER_REFRESH_TOKEN_TTL_DAYS=%s, SERVICE_ACCESS_TOKEN_TTL_MINUTES=%s",
    settings.userAccessTokenTtlMinutes,
    settings.userRefreshTokenTtlDays,
    settings.serviceAccessTokenTtlMinutes,
  );

  app.listen(settings.port, settings.host, () => {
    console.info("Web Service started on http://%s:%s (env=%s)", settings.host, settings.port, settings.env);
  });
}
