import fs from "node:fs";
import jwt, { JwtPayload } from "jsonwebtoken";
import { v4 as uuidv4 } from "uuid";

import { Settings } from "./config";

export interface UserAccessClaims extends JwtPayload {
  sub: string;
  login?: string;
  role: string;
  token_kind: string;
  principal_type: string;
}

export interface ServiceAccessClaims extends JwtPayload {
  sub: string;
  token_kind: string;
  principal_type: string;
}

export class AuthTokenError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AuthTokenError";
  }
}

function asPayload(decoded: string | JwtPayload): JwtPayload {
  if (typeof decoded === "string") {
    throw new AuthTokenError("invalid JWT payload");
  }
  return decoded;
}

export class TokenSecurity {
  private readonly authPublicKey: string;
  private readonly servicePrivateKey: string;

  constructor(private readonly settings: Settings) {
    this.authPublicKey = fs.readFileSync(settings.authPublicKeyPath, "utf-8");
    this.servicePrivateKey = fs.readFileSync(settings.servicePrivateKeyPath, "utf-8");
  }

  extractBearerToken(rawHeader: unknown, headerName: string): string {
    if (typeof rawHeader !== "string") {
      throw new AuthTokenError(`${headerName} header is required`);
    }

    const prefix = "Bearer ";
    if (!rawHeader.startsWith(prefix)) {
      throw new AuthTokenError(`${headerName} must use 'Bearer <token>' format`);
    }

    const token = rawHeader.slice(prefix.length).trim();
    if (token.length === 0) {
      throw new AuthTokenError(`${headerName} bearer token is empty`);
    }

    return token;
  }

  verifyUserAccessToken(token: string): UserAccessClaims {
    try {
      const decoded = jwt.verify(token, this.authPublicKey, {
        algorithms: ["RS256"],
        issuer: this.settings.authTokenIssuer,
        audience: this.settings.userAccessTokenAudience,
        clockTolerance: this.settings.clockSkewSeconds,
      });

      const payload = asPayload(decoded);

      if (payload.token_kind !== "access") {
        throw new AuthTokenError("token_kind must be 'access'");
      }
      if (payload.principal_type !== "user") {
        throw new AuthTokenError("principal_type must be 'user'");
      }
      if (typeof payload.sub !== "string" || payload.sub.trim() === "") {
        throw new AuthTokenError("user token subject is empty");
      }
      if (typeof payload.role !== "string" || payload.role.trim() === "") {
        throw new AuthTokenError("user token role is empty");
      }

      return payload as UserAccessClaims;
    } catch (error) {
      if (error instanceof AuthTokenError) {
        throw error;
      }
      throw new AuthTokenError("invalid user JWT token");
    }
  }

  verifyServiceAccessToken(token: string, expectedAudience: string): ServiceAccessClaims {
    try {
      const decoded = jwt.verify(token, this.authPublicKey, {
        algorithms: ["RS256"],
        issuer: this.settings.authTokenIssuer,
        audience: expectedAudience,
        clockTolerance: this.settings.clockSkewSeconds,
      });

      const payload = asPayload(decoded);

      if (payload.token_kind !== "access") {
        throw new AuthTokenError("service token token_kind must be 'access'");
      }
      if (payload.principal_type !== "service") {
        throw new AuthTokenError("service token principal_type must be 'service'");
      }
      if (typeof payload.sub !== "string" || payload.sub.trim() === "") {
        throw new AuthTokenError("service token subject is empty");
      }

      return payload as ServiceAccessClaims;
    } catch (error) {
      if (error instanceof AuthTokenError) {
        throw error;
      }
      throw new AuthTokenError("invalid service JWT token");
    }
  }

  buildServiceAssertion(): string {
    const now = Math.floor(Date.now() / 1000);
    const expiresAt = now + this.settings.serviceAssertionTtlSeconds;

    return jwt.sign(
      {
        iss: this.settings.serviceId,
        sub: this.settings.serviceId,
        aud: this.settings.serviceAssertionAudience,
        iat: now,
        nbf: now,
        exp: expiresAt,
        jti: uuidv4(),
      },
      this.servicePrivateKey,
      {
        algorithm: "RS256",
      },
    );
  }
}
