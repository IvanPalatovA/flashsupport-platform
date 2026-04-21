import { UserRole } from "../domain";
import { TokenPair } from "./authClient";
import { UserAccessClaims } from "./security";

export interface SessionRecord {
  sessionId: string;
  userId: string;
  login: string;
  role: UserRole;
  accessToken: string;
  refreshToken: string;
  accessExpiresAt: number;
  refreshExpiresAt: number;
  updatedAt: number;
}

export class SessionStore {
  private readonly sessions = new Map<string, SessionRecord>();

  constructor(private readonly ttlSeconds: number) {}

  private nowUnix(): number {
    return Math.floor(Date.now() / 1000);
  }

  private ensureExp(claims: UserAccessClaims): number {
    if (typeof claims.exp !== "number") {
      throw new Error("JWT access token is missing exp claim");
    }
    return claims.exp;
  }

  upsert(sessionId: string, claims: UserAccessClaims, tokenPair: TokenPair): SessionRecord {
    const now = this.nowUnix();
    const accessExp = this.ensureExp(claims);
    const refreshExp = now + tokenPair.refreshExpiresIn;

    const role = claims.role as UserRole;
    const login = typeof claims.login === "string" ? claims.login : claims.sub;

    const record: SessionRecord = {
      sessionId,
      userId: claims.sub,
      login,
      role,
      accessToken: tokenPair.accessToken,
      refreshToken: tokenPair.refreshToken,
      accessExpiresAt: accessExp,
      refreshExpiresAt: refreshExp,
      updatedAt: now,
    };

    this.sessions.set(sessionId, record);
    return record;
  }

  get(sessionId: string): SessionRecord | null {
    const record = this.sessions.get(sessionId);
    if (!record) {
      return null;
    }

    const now = this.nowUnix();
    if (now - record.updatedAt > this.ttlSeconds || now > record.refreshExpiresAt) {
      this.sessions.delete(sessionId);
      return null;
    }

    return record;
  }

  remove(sessionId: string): void {
    this.sessions.delete(sessionId);
  }
}
