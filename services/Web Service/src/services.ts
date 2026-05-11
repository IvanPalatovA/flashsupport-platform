import { AxiosError, isAxiosError } from "axios";
import { v4 as uuidv4 } from "uuid";

import {
  AccountRecord,
  ChatMessage,
  ChatStatus,
  ChatSummary,
  ChatThread,
  DeliveryRoute,
  KnowledgeRequest,
  OperatorAction,
  UserRole,
} from "./domain";
import { AuthClient, TokenPair } from "./infrastructure/authClient";
import { Settings } from "./infrastructure/config";
import { UpstreamClients } from "./infrastructure/httpClients";
import { SessionRecord, SessionStore } from "./infrastructure/sessions";
import { AuthTokenError, TokenSecurity, UserAccessClaims } from "./infrastructure/security";

interface CachedServiceToken {
  token: string;
  expiresAtUnix: number;
}

interface OrchestratorUserResponse {
  chat_id: string;
  route: DeliveryRoute;
  chat_status: ChatStatus;
  message: string;
  queue_item_id?: string | null;
  rag_results?: Array<{
    document_title: string;
    text: string;
    score: number;
  }>;
}

interface OrchestratorActionResponse {
  chat_id: string;
  chat_status: ChatStatus;
  message: string;
}

interface SessionProfile {
  userId: string;
  login: string;
  role: UserRole;
  operatorCallThresholdMessages: number;
}

export class WebServiceError extends Error {
  constructor(
    public readonly statusCode: number,
    message: string,
  ) {
    super(message);
    this.name = "WebServiceError";
  }
}

export class WebService {
  private readonly chats = new Map<string, ChatThread>();
  private readonly chatsByOwner = new Map<string, Set<string>>();
  private readonly knowledgeRequests = new Map<string, KnowledgeRequest>();
  private readonly accounts = new Map<string, AccountRecord>();
  private readonly serviceTokenCache = new Map<string, CachedServiceToken>();

  constructor(
    private readonly settings: Settings,
    private readonly authClient: AuthClient,
    private readonly upstream: UpstreamClients,
    private readonly tokenSecurity: TokenSecurity,
    private readonly sessionStore: SessionStore,
  ) {}

  private nowUnix(): number {
    return Math.floor(Date.now() / 1000);
  }

  private nowIso(): string {
    return new Date().toISOString();
  }

  private normalizeRole(rawRole: string): UserRole {
    if (rawRole === "registered_user" || rawRole === "operator" || rawRole === "admin") {
      return rawRole;
    }
    throw new WebServiceError(403, `Unsupported role '${rawRole}' for Web Service`);
  }

  private toProfile(session: SessionRecord): SessionProfile {
    return {
      userId: session.userId,
      login: session.login,
      role: session.role,
      operatorCallThresholdMessages: this.settings.operatorCallThresholdMessages,
    };
  }

  private upsertAccount(userId: string, login: string, role: UserRole): void {
    this.accounts.set(userId, {
      userId,
      login,
      role,
      isBlocked: this.accounts.get(userId)?.isBlocked ?? false,
      updatedAt: this.nowIso(),
    });
  }

  private makeSessionTokenPair(session: SessionRecord): TokenPair {
    return {
      accessToken: session.accessToken,
      refreshToken: session.refreshToken,
      accessExpiresIn: Math.max(0, session.accessExpiresAt - this.nowUnix()),
      refreshExpiresIn: Math.max(0, session.refreshExpiresAt - this.nowUnix()),
    };
  }

  private async refreshUserSession(sessionId: string, session: SessionRecord): Promise<{ session: SessionRecord; claims: UserAccessClaims }> {
    try {
      const refreshed = await this.authClient.refresh(session.refreshToken);
      const claims = this.tokenSecurity.verifyUserAccessToken(refreshed.accessToken);
      const role = this.normalizeRole(claims.role);

      const updated = this.sessionStore.upsert(sessionId, { ...claims, role }, refreshed);
      this.upsertAccount(updated.userId, updated.login, updated.role);
      return { session: updated, claims: { ...claims, role } };
    } catch (error) {
      throw this.mapError(error, "Unable to refresh user session", 401);
    }
  }

  private async requireSession(sessionId: string | undefined): Promise<{ session: SessionRecord; claims: UserAccessClaims }> {
    if (!sessionId) {
      throw new WebServiceError(401, "Session is not established");
    }

    const current = this.sessionStore.get(sessionId);
    if (!current) {
      throw new WebServiceError(401, "Session is expired or invalid");
    }

    let claims: UserAccessClaims;

    try {
      claims = this.tokenSecurity.verifyUserAccessToken(current.accessToken);
    } catch (error) {
      if (error instanceof AuthTokenError) {
        return this.refreshUserSession(sessionId, current);
      }
      throw error;
    }

    const now = this.nowUnix();
    const exp = typeof claims.exp === "number" ? claims.exp : now;
    if (exp - now <= this.settings.userTokenRefreshSkewSeconds) {
      return this.refreshUserSession(sessionId, current);
    }

    const role = this.normalizeRole(claims.role);
    if (role !== current.role) {
      const updated = this.sessionStore.upsert(sessionId, { ...claims, role }, this.makeSessionTokenPair(current));
      this.upsertAccount(updated.userId, updated.login, updated.role);
      return { session: updated, claims: { ...claims, role } };
    }

    this.upsertAccount(current.userId, current.login, current.role);
    return { session: current, claims: { ...claims, role } };
  }

  private async getServiceToken(audience: string): Promise<string> {
    const cached = this.serviceTokenCache.get(audience);
    const now = this.nowUnix();

    if (cached && cached.expiresAtUnix - now > this.settings.serviceTokenRefreshSkewSeconds) {
      try {
        this.tokenSecurity.verifyServiceAccessToken(cached.token, audience);
        return cached.token;
      } catch {
        this.serviceTokenCache.delete(audience);
      }
    }

    try {
      const assertion = this.tokenSecurity.buildServiceAssertion();
      const issued = await this.authClient.issueServiceToken(this.settings.serviceId, audience, assertion);
      const claims = this.tokenSecurity.verifyServiceAccessToken(issued.accessToken, audience);
      const expiresAtUnix = typeof claims.exp === "number" ? claims.exp : now + issued.accessExpiresIn;

      this.serviceTokenCache.set(audience, {
        token: issued.accessToken,
        expiresAtUnix,
      });

      console.info(
        "Refreshed service JWT for audience='%s', expires_in=%ss",
        audience,
        Math.max(0, expiresAtUnix - now),
      );

      return issued.accessToken;
    } catch (error) {
      throw this.mapError(error, "Unable to refresh service token", 502);
    }
  }

  private mapAxiosError(error: AxiosError, fallbackMessage: string, fallbackStatus = 502): WebServiceError {
    const payload = error.response?.data as { detail?: string; message?: string } | undefined;
    const detail = payload?.detail ?? payload?.message;
    return new WebServiceError(error.response?.status ?? fallbackStatus, detail ?? fallbackMessage);
  }

  private mapError(error: unknown, fallbackMessage: string, fallbackStatus = 500): WebServiceError {
    if (error instanceof WebServiceError) {
      return error;
    }
    if (isAxiosError(error)) {
      return this.mapAxiosError(error, fallbackMessage, fallbackStatus);
    }
    return new WebServiceError(fallbackStatus, fallbackMessage);
  }

  private getChatOrThrow(chatId: string): ChatThread {
    const chat = this.chats.get(chatId);
    if (!chat) {
      throw new WebServiceError(404, `Chat '${chatId}' not found`);
    }
    return chat;
  }

  private ensureChatAccess(chat: ChatThread, role: UserRole, userId: string): void {
    if (role === "registered_user" && chat.ownerUserId !== userId) {
      throw new WebServiceError(403, "Chat access denied");
    }
  }

  private addMessage(chat: ChatThread, senderRole: ChatMessage["senderRole"], senderId: string, text: string): ChatMessage {
    const message: ChatMessage = {
      messageId: uuidv4(),
      chatId: chat.chatId,
      senderRole,
      senderId,
      text,
      createdAt: this.nowIso(),
    };
    chat.messages.push(message);
    chat.updatedAt = message.createdAt;
    return message;
  }

  private countUserMessages(chat: ChatThread): number {
    return chat.messages.filter((message) => message.senderRole === "registered_user").length;
  }

  private toSummary(chat: ChatThread): ChatSummary {
    const preview = chat.messages.length > 0 ? chat.messages[chat.messages.length - 1].text : "";
    return {
      chatId: chat.chatId,
      title: chat.title,
      status: chat.status,
      escalatedToOperator: chat.escalatedToOperator,
      assignedOperatorId: chat.assignedOperatorId,
      updatedAt: chat.updatedAt,
      preview,
      userMessageCount: this.countUserMessages(chat),
    };
  }

  private async callChatOrchestrator<T>(
    path: string,
    userToken: string,
    payload: Record<string, unknown>,
  ): Promise<T> {
    try {
      const serviceToken = await this.getServiceToken(this.settings.serviceTokenAudienceChatOrchestrator);
      const response = await this.upstream.chatOrchestrator.post(path, payload, {
        headers: {
          Authorization: `Bearer ${userToken}`,
          "X-Service-Authorization": `Bearer ${serviceToken}`,
          "X-Service-Name": this.settings.serviceId,
        },
      });
      return response.data as T;
    } catch (error) {
      throw this.mapError(error, `Chat Orchestrator call failed: ${path}`, 502);
    }
  }

  private async callRag<T>(userToken: string, payload: Record<string, unknown>): Promise<T> {
    try {
      const serviceToken = await this.getServiceToken(this.settings.serviceTokenAudienceRagService);
      const response = await this.upstream.ragEngine.post("/search", payload, {
        headers: {
          Authorization: `Bearer ${userToken}`,
          "X-Service-Authorization": `Bearer ${serviceToken}`,
          "X-Service-Name": this.settings.serviceId,
        },
      });
      return response.data as T;
    } catch (error) {
      throw this.mapError(error, "RAG Engine call failed: /search", 502);
    }
  }

  async registerAndLogin(
    sessionId: string,
    login: string,
    password: string,
    role: UserRole,
  ): Promise<{ profile: SessionProfile; tokenPair: TokenPair }> {
    try {
      await this.authClient.register(login, password, role);
      const tokenPair = await this.authClient.login(login, password);
      const claims = this.tokenSecurity.verifyUserAccessToken(tokenPair.accessToken);
      const normalizedRole = this.normalizeRole(claims.role);
      const session = this.sessionStore.upsert(sessionId, { ...claims, role: normalizedRole }, tokenPair);
      this.upsertAccount(session.userId, session.login, session.role);

      return {
        profile: this.toProfile(session),
        tokenPair,
      };
    } catch (error) {
      throw this.mapError(error, "Unable to register and login", 400);
    }
  }

  async login(sessionId: string, login: string, password: string): Promise<{ profile: SessionProfile; tokenPair: TokenPair }> {
    try {
      const tokenPair = await this.authClient.login(login, password);
      const claims = this.tokenSecurity.verifyUserAccessToken(tokenPair.accessToken);
      const normalizedRole = this.normalizeRole(claims.role);
      const session = this.sessionStore.upsert(sessionId, { ...claims, role: normalizedRole }, tokenPair);
      this.upsertAccount(session.userId, session.login, session.role);

      return {
        profile: this.toProfile(session),
        tokenPair,
      };
    } catch (error) {
      throw this.mapError(error, "Unable to login", 401);
    }
  }

  async refresh(sessionId: string | undefined): Promise<{ profile: SessionProfile; tokenPair: TokenPair }> {
    if (!sessionId) {
      throw new WebServiceError(401, "Session is missing");
    }

    const existing = this.sessionStore.get(sessionId);
    if (!existing) {
      throw new WebServiceError(401, "Session is missing or expired");
    }

    const refreshed = await this.refreshUserSession(sessionId, existing);

    return {
      profile: this.toProfile(refreshed.session),
      tokenPair: this.makeSessionTokenPair(refreshed.session),
    };
  }

  async me(sessionId: string | undefined): Promise<SessionProfile> {
    const { session } = await this.requireSession(sessionId);
    return this.toProfile(session);
  }

  logout(sessionId: string | undefined): void {
    if (!sessionId) {
      return;
    }
    this.sessionStore.remove(sessionId);
  }

  async listChats(sessionId: string | undefined): Promise<ChatSummary[]> {
    const { session } = await this.requireSession(sessionId);

    let chats: ChatThread[];
    if (session.role === "registered_user") {
      const userChatIds = this.chatsByOwner.get(session.userId) ?? new Set<string>();
      chats = [...userChatIds]
        .map((chatId) => this.chats.get(chatId))
        .filter((item): item is ChatThread => item !== undefined);
    } else if (session.role === "operator") {
      chats = [...this.chats.values()].filter((chat) => chat.escalatedToOperator || chat.assignedOperatorId === session.userId);
    } else {
      chats = [...this.chats.values()];
    }

    return chats
      .sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1))
      .map((chat) => this.toSummary(chat));
  }

  async createChat(sessionId: string | undefined, title?: string): Promise<ChatSummary> {
    const { session } = await this.requireSession(sessionId);
    if (session.role !== "registered_user") {
      throw new WebServiceError(403, "Only registered users can create support chats");
    }

    const createdAt = this.nowIso();
    const chatId = uuidv4();
    const normalizedTitle = title && title.trim() !== "" ? title.trim() : `Support chat ${chatId.slice(0, 8)}`;

    const chat: ChatThread = {
      chatId,
      title: normalizedTitle,
      ownerUserId: session.userId,
      status: "open",
      escalatedToOperator: false,
      assignedOperatorId: null,
      messages: [],
      createdAt,
      updatedAt: createdAt,
    };

    this.chats.set(chatId, chat);
    const chatIds = this.chatsByOwner.get(session.userId) ?? new Set<string>();
    chatIds.add(chatId);
    this.chatsByOwner.set(session.userId, chatIds);

    return this.toSummary(chat);
  }

  async getMessages(sessionId: string | undefined, chatId: string): Promise<ChatMessage[]> {
    const { session } = await this.requireSession(sessionId);
    const chat = this.getChatOrThrow(chatId);
    this.ensureChatAccess(chat, session.role, session.userId);

    return chat.messages;
  }

  private formatRagReply(
    orchestratorMessage: string,
    ragResults: Array<{ document_title: string; text: string; score: number }> | undefined,
  ): string {
    if (!ragResults || ragResults.length === 0) {
      return orchestratorMessage;
    }

    const fragments = ragResults.slice(0, 3).map((item) => `${item.document_title}: ${item.text}`);
    return `${orchestratorMessage}\n\n${fragments.join("\n\n")}`;
  }

  private canCallOperator(chat: ChatThread): boolean {
    const sent = this.countUserMessages(chat);
    return sent > this.settings.operatorCallThresholdMessages;
  }

  async sendUserMessage(
    sessionId: string | undefined,
    chatId: string,
    text: string,
  ): Promise<{
    summary: ChatSummary;
    route: DeliveryRoute;
    chatStatus: ChatStatus;
    canCallOperator: boolean;
    orchestratorMessage: string;
    messages: ChatMessage[];
  }> {
    const { session } = await this.requireSession(sessionId);
    if (session.role !== "registered_user") {
      throw new WebServiceError(403, "Only registered users can send customer messages");
    }

    const chat = this.getChatOrThrow(chatId);
    this.ensureChatAccess(chat, session.role, session.userId);

    if (chat.status === "closed" || chat.status === "blocked") {
      throw new WebServiceError(409, `Chat '${chatId}' is ${chat.status}`);
    }

    this.addMessage(chat, "registered_user", session.userId, text);

    const response = await this.callChatOrchestrator<OrchestratorUserResponse>("/messages/user", session.accessToken, {
      chat_id: chat.chatId,
      sender_id: session.userId,
      sender_role: "registered_user",
      text,
      request_operator: chat.escalatedToOperator,
    });

    chat.status = response.chat_status;
    if (response.route === "operator_queue") {
      chat.escalatedToOperator = true;
    }

    const replyText = this.formatRagReply(response.message, response.rag_results);
    this.addMessage(chat, response.route === "rag_engine" ? "assistant" : "system", "orchestrator", replyText);

    return {
      summary: this.toSummary(chat),
      route: response.route,
      chatStatus: response.chat_status,
      canCallOperator: this.canCallOperator(chat),
      orchestratorMessage: response.message,
      messages: chat.messages,
    };
  }

  async callOperator(
    sessionId: string | undefined,
    chatId: string,
    note?: string,
  ): Promise<{ summary: ChatSummary; chatStatus: ChatStatus; messages: ChatMessage[] }> {
    const { session } = await this.requireSession(sessionId);
    if (session.role !== "registered_user") {
      throw new WebServiceError(403, "Only registered users can request operator assistance");
    }

    const chat = this.getChatOrThrow(chatId);
    this.ensureChatAccess(chat, session.role, session.userId);

    if (!this.canCallOperator(chat)) {
      throw new WebServiceError(
        400,
        `Operator request becomes available after ${this.settings.operatorCallThresholdMessages + 1} messages`,
      );
    }

    const text = note && note.trim() !== "" ? note.trim() : "User requested operator assistance";
    const response = await this.callChatOrchestrator<OrchestratorUserResponse>("/messages/user", session.accessToken, {
      chat_id: chat.chatId,
      sender_id: session.userId,
      sender_role: "registered_user",
      text,
      request_operator: true,
    });

    chat.escalatedToOperator = true;
    chat.status = response.chat_status;
    this.addMessage(chat, "system", "orchestrator", response.message);

    return {
      summary: this.toSummary(chat),
      chatStatus: response.chat_status,
      messages: chat.messages,
    };
  }

  async operatorReply(
    sessionId: string | undefined,
    chatId: string,
    text: string,
  ): Promise<{ summary: ChatSummary; chatStatus: ChatStatus; messages: ChatMessage[] }> {
    const { session } = await this.requireSession(sessionId);
    if (session.role !== "operator") {
      throw new WebServiceError(403, "Only operators can send operator replies");
    }

    const chat = this.getChatOrThrow(chatId);

    const response = await this.callChatOrchestrator<OrchestratorActionResponse>("/messages/operator", session.accessToken, {
      chat_id: chat.chatId,
      operator_id: session.userId,
      recipient_role: "registered_user",
      text,
    });

    chat.assignedOperatorId = session.userId;
    chat.escalatedToOperator = true;
    chat.status = response.chat_status;
    this.addMessage(chat, "operator", session.userId, text);
    if (response.message && response.message.trim() !== "") {
      this.addMessage(chat, "system", "orchestrator", response.message);
    }

    return {
      summary: this.toSummary(chat),
      chatStatus: response.chat_status,
      messages: chat.messages,
    };
  }

  async operatorAction(
    sessionId: string | undefined,
    chatId: string,
    action: OperatorAction,
    note?: string,
  ): Promise<{ summary: ChatSummary; chatStatus: ChatStatus; messages: ChatMessage[] }> {
    const { session } = await this.requireSession(sessionId);
    if (session.role !== "operator") {
      throw new WebServiceError(403, "Only operators can execute operator actions");
    }

    const chat = this.getChatOrThrow(chatId);

    const response = await this.callChatOrchestrator<OrchestratorActionResponse>("/operator/actions", session.accessToken, {
      chat_id: chat.chatId,
      operator_id: session.userId,
      action,
      note: note ?? null,
    });

    chat.status = response.chat_status;
    chat.assignedOperatorId = session.userId;
    if (action === "block_chat") {
      chat.escalatedToOperator = true;
    }

    this.addMessage(chat, "system", "operator", response.message);

    return {
      summary: this.toSummary(chat),
      chatStatus: response.chat_status,
      messages: chat.messages,
    };
  }

  async deleteChat(sessionId: string | undefined, chatId: string): Promise<void> {
    const { session } = await this.requireSession(sessionId);
    if (session.role !== "operator" && session.role !== "admin") {
      throw new WebServiceError(403, "Only operator/admin can delete chats");
    }

    const chat = this.getChatOrThrow(chatId);
    this.chats.delete(chatId);

    const ownerChats = this.chatsByOwner.get(chat.ownerUserId);
    if (ownerChats) {
      ownerChats.delete(chatId);
      this.chatsByOwner.set(chat.ownerUserId, ownerChats);
    }
  }

  async ragSearch(
    sessionId: string | undefined,
    query: string,
    topK: number,
  ): Promise<{ query: string; top_k: number; results: Array<Record<string, unknown>> }> {
    const { session } = await this.requireSession(sessionId);
    if (session.role !== "operator" && session.role !== "admin") {
      throw new WebServiceError(403, "Only operator/admin can query RAG directly");
    }

    return this.callRag<{ query: string; top_k: number; results: Array<Record<string, unknown>> }>(session.accessToken, {
      query,
      top_k: topK,
    });
  }

  private buildKnowledgeDraft(chat: ChatThread): { question: string; answer: string } {
    const userText = [...chat.messages].reverse().find((item) => item.senderRole === "registered_user")?.text;
    const operatorText = [...chat.messages].reverse().find((item) => item.senderRole === "operator")?.text;

    return {
      question: userText ?? "Describe the user issue",
      answer: operatorText ?? "Provide operator answer",
    };
  }

  async createKnowledgeRequest(
    sessionId: string | undefined,
    chatId: string,
    question?: string,
    answer?: string,
  ): Promise<KnowledgeRequest> {
    const { session } = await this.requireSession(sessionId);
    if (session.role !== "operator") {
      throw new WebServiceError(403, "Only operators can submit knowledge requests");
    }

    const chat = this.getChatOrThrow(chatId);
    const draft = this.buildKnowledgeDraft(chat);

    const request: KnowledgeRequest = {
      requestId: uuidv4(),
      chatId,
      question: question && question.trim() !== "" ? question.trim() : draft.question,
      answer: answer && answer.trim() !== "" ? answer.trim() : draft.answer,
      createdBy: session.userId,
      createdAt: this.nowIso(),
      status: "pending",
      reviewedBy: null,
      reviewedAt: null,
      dispatchStatus: "queued",
    };

    this.knowledgeRequests.set(request.requestId, request);
    return request;
  }

  async listKnowledgeRequests(sessionId: string | undefined): Promise<KnowledgeRequest[]> {
    const { session } = await this.requireSession(sessionId);
    if (session.role !== "admin") {
      throw new WebServiceError(403, "Only admins can review knowledge requests");
    }

    return [...this.knowledgeRequests.values()].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
  }

  private async dispatchKnowledgeToPipeline(request: KnowledgeRequest): Promise<"queued" | "sent"> {
    try {
      await this.upstream.knowledgePipeline.post("/v1/knowledge/qa", {
        request_id: request.requestId,
        chat_id: request.chatId,
        question: request.question,
        answer: request.answer,
      });
      return "sent";
    } catch {
      return "queued";
    }
  }

  async approveKnowledgeRequest(sessionId: string | undefined, requestId: string): Promise<KnowledgeRequest> {
    const { session } = await this.requireSession(sessionId);
    if (session.role !== "admin") {
      throw new WebServiceError(403, "Only admins can approve knowledge requests");
    }

    const request = this.knowledgeRequests.get(requestId);
    if (!request) {
      throw new WebServiceError(404, `Knowledge request '${requestId}' not found`);
    }

    request.status = "approved";
    request.reviewedBy = session.userId;
    request.reviewedAt = this.nowIso();
    request.dispatchStatus = await this.dispatchKnowledgeToPipeline(request);

    this.knowledgeRequests.set(requestId, request);
    return request;
  }

  async rejectKnowledgeRequest(sessionId: string | undefined, requestId: string): Promise<KnowledgeRequest> {
    const { session } = await this.requireSession(sessionId);
    if (session.role !== "admin") {
      throw new WebServiceError(403, "Only admins can reject knowledge requests");
    }

    const request = this.knowledgeRequests.get(requestId);
    if (!request) {
      throw new WebServiceError(404, `Knowledge request '${requestId}' not found`);
    }

    request.status = "rejected";
    request.reviewedBy = session.userId;
    request.reviewedAt = this.nowIso();

    this.knowledgeRequests.set(requestId, request);
    return request;
  }

  async listAccounts(sessionId: string | undefined): Promise<AccountRecord[]> {
    const { session } = await this.requireSession(sessionId);
    if (session.role !== "admin") {
      throw new WebServiceError(403, "Only admins can view account list");
    }

    return [...this.accounts.values()].sort((a, b) => (a.login > b.login ? 1 : -1));
  }

  async blockAccount(sessionId: string | undefined, accountId: string, blocked: boolean): Promise<AccountRecord> {
    const { session } = await this.requireSession(sessionId);
    if (session.role !== "admin") {
      throw new WebServiceError(403, "Only admins can block accounts");
    }

    const account = this.accounts.get(accountId);
    if (!account) {
      throw new WebServiceError(404, `Account '${accountId}' not found`);
    }

    account.isBlocked = blocked;
    account.updatedAt = this.nowIso();
    this.accounts.set(accountId, account);
    return account;
  }

  async changeAccountRole(sessionId: string | undefined, accountId: string, role: UserRole): Promise<AccountRecord> {
    const { session } = await this.requireSession(sessionId);
    if (session.role !== "admin") {
      throw new WebServiceError(403, "Only admins can change roles");
    }

    const account = this.accounts.get(accountId);
    if (!account) {
      throw new WebServiceError(404, `Account '${accountId}' not found`);
    }

    account.role = role;
    account.updatedAt = this.nowIso();
    this.accounts.set(accountId, account);
    return account;
  }
}
