import { NextFunction, Request, Response, Router } from "express";
import { v4 as uuidv4 } from "uuid";

import { asBoolean, asOperatorAction, asOptionalString, asPositiveInt, asString, asUserRole } from "./models";
import { Settings } from "./infrastructure/config";
import { WebService, WebServiceError } from "./services";

function asyncHandler(
  handler: (req: Request, res: Response, next: NextFunction) => Promise<void>,
): (req: Request, res: Response, next: NextFunction) => void {
  return (req, res, next) => {
    handler(req, res, next).catch(next);
  };
}

function getSessionId(req: Request, settings: Settings): string | undefined {
  const signed = req.signedCookies?.[settings.sessionCookieName];
  if (typeof signed === "string" && signed !== "") {
    return signed;
  }

  const regular = req.cookies?.[settings.sessionCookieName];
  if (typeof regular === "string" && regular !== "") {
    return regular;
  }

  return undefined;
}

function setSessionCookie(res: Response, settings: Settings, sessionId: string): void {
  res.cookie(settings.sessionCookieName, sessionId, {
    httpOnly: true,
    sameSite: "lax",
    secure: settings.sessionCookieSecure,
    maxAge: settings.sessionTtlSeconds * 1000,
    signed: true,
    path: "/",
  });
}

function clearSessionCookie(res: Response, settings: Settings): void {
  res.clearCookie(settings.sessionCookieName, {
    path: "/",
    sameSite: "lax",
    secure: settings.sessionCookieSecure,
    signed: true,
  });
}

export function createRouter(service: WebService, settings: Settings): Router {
  const router = Router();

  router.post(
    "/auth/register",
    asyncHandler(async (req, res) => {
      const login = asString(req.body?.login, "login", 3, 128);
      const password = asString(req.body?.password, "password", 8, 256);
      const role = req.body?.role ? asUserRole(req.body.role, "role") : "registered_user";

      const sessionId = uuidv4();
      const result = await service.registerAndLogin(sessionId, login, password, role);
      setSessionCookie(res, settings, sessionId);

      res.status(201).json({
        profile: result.profile,
        token_meta: {
          access_expires_in: result.tokenPair.accessExpiresIn,
          refresh_expires_in: result.tokenPair.refreshExpiresIn,
        },
      });
    }),
  );

  router.post(
    "/auth/login",
    asyncHandler(async (req, res) => {
      const login = asString(req.body?.login, "login", 3, 128);
      const password = asString(req.body?.password, "password", 8, 256);

      const sessionId = uuidv4();
      const result = await service.login(sessionId, login, password);
      setSessionCookie(res, settings, sessionId);

      res.status(200).json({
        profile: result.profile,
        token_meta: {
          access_expires_in: result.tokenPair.accessExpiresIn,
          refresh_expires_in: result.tokenPair.refreshExpiresIn,
        },
      });
    }),
  );

  router.post(
    "/auth/refresh",
    asyncHandler(async (req, res) => {
      const sessionId = getSessionId(req, settings);
      const result = await service.refresh(sessionId);
      if (sessionId) {
        setSessionCookie(res, settings, sessionId);
      }

      res.status(200).json({
        profile: result.profile,
        token_meta: {
          access_expires_in: result.tokenPair.accessExpiresIn,
          refresh_expires_in: result.tokenPair.refreshExpiresIn,
        },
      });
    }),
  );

  router.post(
    "/auth/logout",
    asyncHandler(async (req, res) => {
      const sessionId = getSessionId(req, settings);
      service.logout(sessionId);
      clearSessionCookie(res, settings);
      res.status(200).json({ message: "Logged out" });
    }),
  );

  router.get(
    "/auth/me",
    asyncHandler(async (req, res) => {
      const profile = await service.me(getSessionId(req, settings));
      res.status(200).json({ profile });
    }),
  );

  router.get(
    "/chats",
    asyncHandler(async (req, res) => {
      const chats = await service.listChats(getSessionId(req, settings));
      res.status(200).json({ chats });
    }),
  );

  router.post(
    "/chats",
    asyncHandler(async (req, res) => {
      const title = asOptionalString(req.body?.title, "title", 120);
      const chat = await service.createChat(getSessionId(req, settings), title);
      res.status(201).json({ chat });
    }),
  );

  router.get(
    "/chats/:chatId/messages",
    asyncHandler(async (req, res) => {
      const chatId = asString(req.params.chatId, "chatId", 2, 128);
      const messages = await service.getMessages(getSessionId(req, settings), chatId);
      res.status(200).json({ messages });
    }),
  );

  router.post(
    "/chats/:chatId/messages",
    asyncHandler(async (req, res) => {
      const chatId = asString(req.params.chatId, "chatId", 2, 128);
      const text = asString(req.body?.text, "text", 1, 4000);
      const payload = await service.sendUserMessage(getSessionId(req, settings), chatId, text);
      res.status(200).json(payload);
    }),
  );

  router.post(
    "/chats/:chatId/call-operator",
    asyncHandler(async (req, res) => {
      const chatId = asString(req.params.chatId, "chatId", 2, 128);
      const note = asOptionalString(req.body?.note, "note", 1000);
      const payload = await service.callOperator(getSessionId(req, settings), chatId, note);
      res.status(200).json(payload);
    }),
  );

  router.post(
    "/chats/:chatId/operator-reply",
    asyncHandler(async (req, res) => {
      const chatId = asString(req.params.chatId, "chatId", 2, 128);
      const text = asString(req.body?.text, "text", 1, 4000);
      const payload = await service.operatorReply(getSessionId(req, settings), chatId, text);
      res.status(200).json(payload);
    }),
  );

  router.post(
    "/chats/:chatId/operator-action",
    asyncHandler(async (req, res) => {
      const chatId = asString(req.params.chatId, "chatId", 2, 128);
      const action = asOperatorAction(req.body?.action, "action");
      const note = asOptionalString(req.body?.note, "note", 1000);
      const payload = await service.operatorAction(getSessionId(req, settings), chatId, action, note);
      res.status(200).json(payload);
    }),
  );

  router.delete(
    "/chats/:chatId",
    asyncHandler(async (req, res) => {
      const chatId = asString(req.params.chatId, "chatId", 2, 128);
      await service.deleteChat(getSessionId(req, settings), chatId);
      res.status(204).send();
    }),
  );

  router.post(
    "/rag/search",
    asyncHandler(async (req, res) => {
      const query = asString(req.body?.query, "query", 2, 4000);
      const topK = asPositiveInt(req.body?.top_k, "top_k", 3, 1, 20);
      const payload = await service.ragSearch(getSessionId(req, settings), query, topK);
      res.status(200).json(payload);
    }),
  );

  router.post(
    "/operator/knowledge-requests",
    asyncHandler(async (req, res) => {
      const chatId = asString(req.body?.chat_id, "chat_id", 2, 128);
      const question = asOptionalString(req.body?.question, "question", 4000);
      const answer = asOptionalString(req.body?.answer, "answer", 4000);
      const payload = await service.createKnowledgeRequest(getSessionId(req, settings), chatId, question, answer);
      res.status(201).json(payload);
    }),
  );

  router.get(
    "/admin/knowledge-requests",
    asyncHandler(async (req, res) => {
      const payload = await service.listKnowledgeRequests(getSessionId(req, settings));
      res.status(200).json({ requests: payload });
    }),
  );

  router.post(
    "/admin/knowledge-requests/:requestId/approve",
    asyncHandler(async (req, res) => {
      const requestId = asString(req.params.requestId, "requestId", 2, 128);
      const payload = await service.approveKnowledgeRequest(getSessionId(req, settings), requestId);
      res.status(200).json(payload);
    }),
  );

  router.post(
    "/admin/knowledge-requests/:requestId/reject",
    asyncHandler(async (req, res) => {
      const requestId = asString(req.params.requestId, "requestId", 2, 128);
      const payload = await service.rejectKnowledgeRequest(getSessionId(req, settings), requestId);
      res.status(200).json(payload);
    }),
  );

  router.get(
    "/admin/accounts",
    asyncHandler(async (req, res) => {
      const accounts = await service.listAccounts(getSessionId(req, settings));
      res.status(200).json({ accounts });
    }),
  );

  router.post(
    "/admin/accounts/:accountId/block",
    asyncHandler(async (req, res) => {
      const accountId = asString(req.params.accountId, "accountId", 2, 128);
      const blocked = req.body?.blocked === undefined ? true : asBoolean(req.body.blocked, "blocked");
      const account = await service.blockAccount(getSessionId(req, settings), accountId, blocked);
      res.status(200).json(account);
    }),
  );

  router.post(
    "/admin/accounts/:accountId/role",
    asyncHandler(async (req, res) => {
      const accountId = asString(req.params.accountId, "accountId", 2, 128);
      const role = asUserRole(req.body?.role, "role");
      const account = await service.changeAccountRole(getSessionId(req, settings), accountId, role);
      res.status(200).json(account);
    }),
  );

  router.use((error: unknown, _req: Request, res: Response, _next: NextFunction) => {
    if (error instanceof WebServiceError) {
      res.status(error.statusCode).json({ detail: error.message });
      return;
    }

    if (error instanceof Error) {
      if (error.message.includes("must be")) {
        res.status(422).json({ detail: error.message });
        return;
      }
      res.status(500).json({ detail: error.message });
      return;
    }

    res.status(500).json({ detail: "Unexpected error" });
  });

  return router;
}
