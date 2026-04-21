import axios, { AxiosInstance } from "axios";

import { UserRole } from "../domain";
import { Settings } from "./config";

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
  accessExpiresIn: number;
  refreshExpiresIn: number;
}

export interface ServiceTokenResponse {
  accessToken: string;
  accessExpiresIn: number;
}

function assertTokenPairShape(raw: Record<string, unknown>): TokenPair {
  const accessToken = raw.access_token;
  const refreshToken = raw.refresh_token;
  const accessExpiresIn = raw.access_expires_in;
  const refreshExpiresIn = raw.refresh_expires_in;

  if (typeof accessToken !== "string" || typeof refreshToken !== "string") {
    throw new Error("Auth Service returned invalid token pair");
  }

  return {
    accessToken,
    refreshToken,
    accessExpiresIn: Number(accessExpiresIn),
    refreshExpiresIn: Number(refreshExpiresIn),
  };
}

export class AuthClient {
  private readonly client: AxiosInstance;

  constructor(settings: Settings) {
    this.client = axios.create({
      baseURL: settings.authServiceUrl,
      timeout: settings.requestTimeoutSeconds * 1000,
      headers: {
        "Content-Type": "application/json",
      },
    });
  }

  async register(login: string, password: string, role: UserRole): Promise<void> {
    await this.client.post("/auth/register", { login, password, role });
  }

  async login(login: string, password: string): Promise<TokenPair> {
    const response = await this.client.post("/auth/login", { login, password });
    return assertTokenPairShape(response.data as Record<string, unknown>);
  }

  async refresh(refreshToken: string): Promise<TokenPair> {
    const response = await this.client.post("/auth/refresh", {
      refresh_token: refreshToken,
    });
    return assertTokenPairShape(response.data as Record<string, unknown>);
  }

  async issueServiceToken(serviceId: string, audience: string, assertion: string): Promise<ServiceTokenResponse> {
    const response = await this.client.post("/auth/service-token", {
      service_id: serviceId,
      audience,
      assertion,
    });

    const payload = response.data as Record<string, unknown>;
    if (typeof payload.access_token !== "string") {
      throw new Error("Auth Service returned invalid service token payload");
    }

    return {
      accessToken: payload.access_token,
      accessExpiresIn: Number(payload.access_expires_in),
    };
  }
}
