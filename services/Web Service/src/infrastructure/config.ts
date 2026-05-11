import fs from "node:fs";
import path from "node:path";
import YAML from "yaml";

export interface Settings {
  appName: string;
  env: string;
  host: string;
  port: number;
  logLevel: string;
  requestTimeoutSeconds: number;
  authServiceUrl: string;
  chatOrchestratorUrl: string;
  ragEngineUrl: string;
  knowledgePipelineUrl: string;
  authPublicKeyPath: string;
  authTokenIssuer: string;
  userAccessTokenAudience: string;
  serviceId: string;
  servicePrivateKeyPath: string;
  serviceAssertionAudience: string;
  serviceAssertionTtlSeconds: number;
  serviceTokenRefreshSkewSeconds: number;
  userTokenRefreshSkewSeconds: number;
  serviceTokenAudienceChatOrchestrator: string;
  serviceTokenAudienceRagService: string;
  operatorCallThresholdMessages: number;
  sessionCookieName: string;
  sessionCookieSecure: boolean;
  sessionTtlSeconds: number;
  cookieSecret: string;
  clockSkewSeconds: number;
  userAccessTokenTtlMinutes: number;
  userRefreshTokenTtlDays: number;
  serviceAccessTokenTtlMinutes: number;
}

let cachedSettings: Settings | null = null;

function readYaml(filePath: string): Record<string, unknown> {
  if (!fs.existsSync(filePath)) {
    return {};
  }

  const content = fs.readFileSync(filePath, "utf-8");
  const parsed = YAML.parse(content);

  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return {};
  }

  return parsed as Record<string, unknown>;
}

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value || value.trim() === "") {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

function getFromEnvOrYaml(
  envName: string,
  envValue: string | undefined,
  data: Record<string, unknown>,
  key: string,
): string {
  if (envValue && envValue.trim() !== "") {
    return envValue;
  }

  const value = data[key];
  if (typeof value === "string" && value.trim() !== "") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  throw new Error(
    `Missing required setting '${key}' for WEB_SERVICE_ENV='${envName}'. ` +
      `Set env var or define it in config/${envName}.yaml or config/base.yaml`,
  );
}

function asInt(raw: string, fieldName: string): number {
  const value = Number.parseInt(raw, 10);
  if (!Number.isFinite(value)) {
    throw new Error(`${fieldName} must be an integer`);
  }
  return value;
}

function asFloat(raw: string, fieldName: string): number {
  const value = Number.parseFloat(raw);
  if (!Number.isFinite(value)) {
    throw new Error(`${fieldName} must be a number`);
  }
  return value;
}

function asBool(raw: string): boolean {
  return raw.trim().toLowerCase() === "true";
}

function resolvePath(serviceRoot: string, rawPath: string): string {
  if (path.isAbsolute(rawPath)) {
    return rawPath;
  }
  return path.resolve(serviceRoot, rawPath);
}

export function getSettings(): Settings {
  if (cachedSettings) {
    return cachedSettings;
  }

  const serviceRoot = path.resolve(__dirname, "..", "..");
  const configDir = path.join(serviceRoot, "config");

  const envName = requiredEnv("WEB_SERVICE_ENV");
  const envConfigPath = path.join(configDir, `${envName}.yaml`);
  if (!fs.existsSync(envConfigPath)) {
    throw new Error(`Environment config file not found: ${envConfigPath}`);
  }

  const merged = {
    ...readYaml(path.join(configDir, "base.yaml")),
    ...readYaml(envConfigPath),
  };

  const authPublicKeyPath = resolvePath(
    serviceRoot,
    getFromEnvOrYaml(envName, process.env.AUTH_PUBLIC_KEY_PATH, merged, "auth_public_key_path"),
  );

  const servicePrivateKeyPath = resolvePath(
    serviceRoot,
    getFromEnvOrYaml(envName, process.env.SERVICE_PRIVATE_KEY_PATH, merged, "service_private_key_path"),
  );

  cachedSettings = {
    appName: getFromEnvOrYaml(envName, process.env.APP_NAME, merged, "app_name"),
    env: envName,
    host: getFromEnvOrYaml(envName, process.env.APP_HOST, merged, "host"),
    port: asInt(getFromEnvOrYaml(envName, process.env.APP_PORT, merged, "port"), "port"),
    logLevel: getFromEnvOrYaml(envName, process.env.LOG_LEVEL, merged, "log_level"),
    requestTimeoutSeconds: asFloat(
      getFromEnvOrYaml(envName, process.env.REQUEST_TIMEOUT_SECONDS, merged, "request_timeout_seconds"),
      "request_timeout_seconds",
    ),
    authServiceUrl: getFromEnvOrYaml(envName, process.env.AUTH_SERVICE_URL, merged, "auth_service_url"),
    chatOrchestratorUrl: getFromEnvOrYaml(
      envName,
      process.env.CHAT_ORCHESTRATOR_URL,
      merged,
      "chat_orchestrator_url",
    ),
    ragEngineUrl: getFromEnvOrYaml(envName, process.env.RAG_ENGINE_URL, merged, "rag_engine_url"),
    knowledgePipelineUrl: getFromEnvOrYaml(
      envName,
      process.env.KNOWLEDGE_PIPELINE_URL,
      merged,
      "knowledge_pipeline_url",
    ),
    authPublicKeyPath,
    authTokenIssuer: getFromEnvOrYaml(envName, process.env.AUTH_TOKEN_ISSUER, merged, "auth_token_issuer"),
    userAccessTokenAudience: getFromEnvOrYaml(
      envName,
      process.env.USER_ACCESS_TOKEN_AUDIENCE,
      merged,
      "user_access_token_audience",
    ),
    serviceId: getFromEnvOrYaml(envName, process.env.SERVICE_ID, merged, "service_id"),
    servicePrivateKeyPath,
    serviceAssertionAudience: getFromEnvOrYaml(
      envName,
      process.env.SERVICE_ASSERTION_AUDIENCE,
      merged,
      "service_assertion_audience",
    ),
    serviceAssertionTtlSeconds: asInt(
      getFromEnvOrYaml(envName, process.env.SERVICE_ASSERTION_TTL_SECONDS, merged, "service_assertion_ttl_seconds"),
      "service_assertion_ttl_seconds",
    ),
    serviceTokenRefreshSkewSeconds: asInt(
      getFromEnvOrYaml(
        envName,
        process.env.SERVICE_TOKEN_REFRESH_SKEW_SECONDS,
        merged,
        "service_token_refresh_skew_seconds",
      ),
      "service_token_refresh_skew_seconds",
    ),
    userTokenRefreshSkewSeconds: asInt(
      getFromEnvOrYaml(
        envName,
        process.env.USER_TOKEN_REFRESH_SKEW_SECONDS,
        merged,
        "user_token_refresh_skew_seconds",
      ),
      "user_token_refresh_skew_seconds",
    ),
    serviceTokenAudienceChatOrchestrator: getFromEnvOrYaml(
      envName,
      process.env.SERVICE_TOKEN_AUDIENCE_CHAT_ORCHESTRATOR,
      merged,
      "service_token_audience_chat_orchestrator",
    ),
    serviceTokenAudienceRagService: getFromEnvOrYaml(
      envName,
      process.env.SERVICE_TOKEN_AUDIENCE_RAG_SERVICE,
      merged,
      "service_token_audience_rag_service",
    ),
    operatorCallThresholdMessages: asInt(
      getFromEnvOrYaml(
        envName,
        process.env.OPERATOR_CALL_THRESHOLD_MESSAGES,
        merged,
        "operator_call_threshold_messages",
      ),
      "operator_call_threshold_messages",
    ),
    sessionCookieName: getFromEnvOrYaml(envName, process.env.SESSION_COOKIE_NAME, merged, "session_cookie_name"),
    sessionCookieSecure: asBool(
      getFromEnvOrYaml(envName, process.env.SESSION_COOKIE_SECURE, merged, "session_cookie_secure"),
    ),
    sessionTtlSeconds: asInt(
      getFromEnvOrYaml(envName, process.env.SESSION_TTL_SECONDS, merged, "session_ttl_seconds"),
      "session_ttl_seconds",
    ),
    cookieSecret: getFromEnvOrYaml(envName, process.env.COOKIE_SECRET, merged, "cookie_secret"),
    clockSkewSeconds: asInt(
      getFromEnvOrYaml(envName, process.env.CLOCK_SKEW_SECONDS, merged, "clock_skew_seconds"),
      "clock_skew_seconds",
    ),
    userAccessTokenTtlMinutes: asInt(
      getFromEnvOrYaml(
        envName,
        process.env.USER_ACCESS_TOKEN_TTL_MINUTES,
        merged,
        "user_access_token_ttl_minutes",
      ),
      "user_access_token_ttl_minutes",
    ),
    userRefreshTokenTtlDays: asInt(
      getFromEnvOrYaml(
        envName,
        process.env.USER_REFRESH_TOKEN_TTL_DAYS,
        merged,
        "user_refresh_token_ttl_days",
      ),
      "user_refresh_token_ttl_days",
    ),
    serviceAccessTokenTtlMinutes: asInt(
      getFromEnvOrYaml(
        envName,
        process.env.SERVICE_ACCESS_TOKEN_TTL_MINUTES,
        merged,
        "service_access_token_ttl_minutes",
      ),
      "service_access_token_ttl_minutes",
    ),
  };

  return cachedSettings;
}
