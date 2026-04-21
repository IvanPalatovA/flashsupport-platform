import React, { FormEvent, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";

type Role = "registered_user" | "operator" | "admin";
type ChatStatus =
  | "open"
  | "waiting_operator"
  | "in_progress_operator"
  | "closed"
  | "blocked"
  | "resolved"
  | "specialist_review";

type SenderRole = Role | "assistant" | "system";

interface Profile {
  userId: string;
  login: string;
  role: Role;
  operatorCallThresholdMessages: number;
}

interface ChatSummary {
  chatId: string;
  title: string;
  status: ChatStatus;
  escalatedToOperator: boolean;
  assignedOperatorId: string | null;
  updatedAt: string;
  preview: string;
  userMessageCount: number;
}

interface ChatMessage {
  messageId: string;
  chatId: string;
  senderRole: SenderRole;
  senderId: string;
  text: string;
  createdAt: string;
}

interface KnowledgeRequest {
  requestId: string;
  chatId: string;
  question: string;
  answer: string;
  createdBy: string;
  createdAt: string;
  status: "pending" | "approved" | "rejected";
  reviewedBy: string | null;
  reviewedAt: string | null;
  dispatchStatus: "queued" | "sent";
}

interface AccountRecord {
  userId: string;
  login: string;
  role: Role;
  isBlocked: boolean;
  updatedAt: string;
}

interface RagResult {
  document_title?: string;
  text?: string;
  score?: number;
}

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    credentials: "include",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = (await response.json()) as Record<string, unknown>;

  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : "Request failed";
    throw new Error(detail);
  }

  return payload as T;
}

function friendlyRole(role: Role): string {
  if (role === "registered_user") {
    return "User";
  }
  if (role === "operator") {
    return "Operator";
  }
  return "Admin";
}

function App(): JSX.Element {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authRole, setAuthRole] = useState<Role>("registered_user");
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [notice, setNotice] = useState<string>("");
  const [noticeError, setNoticeError] = useState(false);

  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [messageText, setMessageText] = useState("");

  const [ragQuery, setRagQuery] = useState("");
  const [ragResults, setRagResults] = useState<RagResult[]>([]);

  const [knowledgeQuestion, setKnowledgeQuestion] = useState("");
  const [knowledgeAnswer, setKnowledgeAnswer] = useState("");

  const [knowledgeRequests, setKnowledgeRequests] = useState<KnowledgeRequest[]>([]);
  const [accounts, setAccounts] = useState<AccountRecord[]>([]);

  const selectedChat = useMemo(
    () => chats.find((item) => item.chatId === selectedChatId) ?? null,
    [chats, selectedChatId],
  );

  const clearNotice = (): void => {
    setNotice("");
    setNoticeError(false);
  };

  const setErrorNotice = (message: string): void => {
    setNotice(message);
    setNoticeError(true);
  };

  const loadProfile = async (): Promise<Profile | null> => {
    try {
      const payload = await api<{ profile: Profile }>("/api/auth/me");
      setProfile(payload.profile);
      return payload.profile;
    } catch {
      setProfile(null);
      return null;
    }
  };

  const loadChats = async (): Promise<void> => {
    if (!profile) {
      setChats([]);
      return;
    }

    try {
      const payload = await api<{ chats: ChatSummary[] }>("/api/chats");
      setChats(payload.chats);
      if (!selectedChatId && payload.chats.length > 0) {
        setSelectedChatId(payload.chats[0].chatId);
      }
      if (selectedChatId && !payload.chats.some((item) => item.chatId === selectedChatId)) {
        setSelectedChatId(payload.chats.length > 0 ? payload.chats[0].chatId : null);
      }
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const loadMessages = async (chatId: string): Promise<void> => {
    try {
      const payload = await api<{ messages: ChatMessage[] }>(`/api/chats/${chatId}/messages`);
      setMessages(payload.messages);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const loadAdminData = async (): Promise<void> => {
    if (!profile || profile.role !== "admin") {
      setKnowledgeRequests([]);
      setAccounts([]);
      return;
    }

    try {
      const [requestsPayload, accountsPayload] = await Promise.all([
        api<{ requests: KnowledgeRequest[] }>("/api/admin/knowledge-requests"),
        api<{ accounts: AccountRecord[] }>("/api/admin/accounts"),
      ]);
      setKnowledgeRequests(requestsPayload.requests);
      setAccounts(accountsPayload.accounts);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  useEffect(() => {
    const bootstrap = async (): Promise<void> => {
      const loadedProfile = await loadProfile();
      if (loadedProfile) {
        await loadChats();
      }
    };

    void bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!profile) {
      return;
    }
    void loadChats();
    if (profile.role === "admin") {
      void loadAdminData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.role]);

  useEffect(() => {
    if (!selectedChatId) {
      setMessages([]);
      return;
    }
    void loadMessages(selectedChatId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedChatId]);

  useEffect(() => {
    if (!profile || profile.role !== "operator") {
      return;
    }
    const lastUser = [...messages].reverse().find((item) => item.senderRole === "registered_user");
    const lastOperator = [...messages].reverse().find((item) => item.senderRole === "operator");

    setKnowledgeQuestion(lastUser?.text ?? "");
    setKnowledgeAnswer(lastOperator?.text ?? "");
  }, [messages, profile]);

  const submitAuth = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    clearNotice();

    try {
      if (authMode === "register") {
        await api<{ profile: Profile }>("/api/auth/register", {
          method: "POST",
          body: JSON.stringify({
            login,
            password,
            role: authRole,
          }),
        });
      } else {
        await api<{ profile: Profile }>("/api/auth/login", {
          method: "POST",
          body: JSON.stringify({
            login,
            password,
          }),
        });
      }

      const loadedProfile = await loadProfile();
      if (loadedProfile) {
        setNotice("Session is active");
        setNoticeError(false);
        await loadChats();
      }
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const createChat = async (): Promise<void> => {
    clearNotice();
    try {
      const payload = await api<{ chat: ChatSummary }>("/api/chats", {
        method: "POST",
        body: JSON.stringify({}),
      });
      await loadChats();
      setSelectedChatId(payload.chat.chatId);
      setNotice("New chat created");
      setNoticeError(false);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const sendMessage = async (): Promise<void> => {
    if (!profile || !selectedChatId || messageText.trim() === "") {
      return;
    }

    clearNotice();

    try {
      if (profile.role === "registered_user") {
        const payload = await api<{ messages: ChatMessage[]; orchestratorMessage: string }>(
          `/api/chats/${selectedChatId}/messages`,
          {
            method: "POST",
            body: JSON.stringify({ text: messageText }),
          },
        );
        setMessages(payload.messages);
        setNotice(payload.orchestratorMessage || "Message sent");
      } else if (profile.role === "operator") {
        const payload = await api<{ messages: ChatMessage[] }>(`/api/chats/${selectedChatId}/operator-reply`, {
          method: "POST",
          body: JSON.stringify({ text: messageText }),
        });
        setMessages(payload.messages);
        setNotice("Operator response sent");
      } else {
        setErrorNotice("Admins do not communicate with customers directly");
        return;
      }

      setMessageText("");
      await loadChats();
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const callOperator = async (): Promise<void> => {
    if (!selectedChatId) {
      return;
    }

    clearNotice();

    try {
      const payload = await api<{ messages: ChatMessage[] }>(`/api/chats/${selectedChatId}/call-operator`, {
        method: "POST",
        body: JSON.stringify({ note: "Please connect me with operator" }),
      });
      setMessages(payload.messages);
      await loadChats();
      setNotice("Operator call has been sent");
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const runOperatorAction = async (action: "close_chat" | "block_chat" | "resolve_chat" | "send_to_specialist_queue") => {
    if (!selectedChatId) {
      return;
    }

    clearNotice();

    try {
      const payload = await api<{ messages: ChatMessage[] }>(`/api/chats/${selectedChatId}/operator-action`, {
        method: "POST",
        body: JSON.stringify({ action }),
      });
      setMessages(payload.messages);
      await loadChats();
      setNotice(`Action '${action}' completed`);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const deleteChat = async (): Promise<void> => {
    if (!selectedChatId) {
      return;
    }

    clearNotice();

    try {
      await api<void>(`/api/chats/${selectedChatId}`, {
        method: "DELETE",
      });
      setSelectedChatId(null);
      setMessages([]);
      await loadChats();
      setNotice("Chat deleted");
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const searchRag = async (): Promise<void> => {
    if (!ragQuery.trim()) {
      return;
    }

    clearNotice();

    try {
      const payload = await api<{ results: RagResult[] }>("/api/rag/search", {
        method: "POST",
        body: JSON.stringify({ query: ragQuery, top_k: 3 }),
      });
      setRagResults(payload.results);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const submitKnowledgeRequest = async (): Promise<void> => {
    if (!selectedChatId) {
      return;
    }

    clearNotice();

    try {
      await api<KnowledgeRequest>("/api/operator/knowledge-requests", {
        method: "POST",
        body: JSON.stringify({
          chat_id: selectedChatId,
          question: knowledgeQuestion,
          answer: knowledgeAnswer,
        }),
      });
      setNotice("Knowledge request sent to admin review");
      setKnowledgeQuestion("");
      setKnowledgeAnswer("");
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const approveRequest = async (requestId: string): Promise<void> => {
    clearNotice();

    try {
      await api<KnowledgeRequest>(`/api/admin/knowledge-requests/${requestId}/approve`, {
        method: "POST",
      });
      setNotice("Request approved");
      await loadAdminData();
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const rejectRequest = async (requestId: string): Promise<void> => {
    clearNotice();

    try {
      await api<KnowledgeRequest>(`/api/admin/knowledge-requests/${requestId}/reject`, {
        method: "POST",
      });
      setNotice("Request rejected");
      await loadAdminData();
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const toggleBlock = async (account: AccountRecord): Promise<void> => {
    clearNotice();

    try {
      await api<AccountRecord>(`/api/admin/accounts/${account.userId}/block`, {
        method: "POST",
        body: JSON.stringify({ blocked: !account.isBlocked }),
      });
      await loadAdminData();
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const updateRole = async (accountId: string, role: Role): Promise<void> => {
    clearNotice();

    try {
      await api<AccountRecord>(`/api/admin/accounts/${accountId}/role`, {
        method: "POST",
        body: JSON.stringify({ role }),
      });
      await loadAdminData();
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const logout = async (): Promise<void> => {
    await api<{ message: string }>("/api/auth/logout", {
      method: "POST",
    });
    setProfile(null);
    setChats([]);
    setMessages([]);
    setSelectedChatId(null);
    setNotice("Logged out");
    setNoticeError(false);
  };

  if (!profile) {
    return (
      <div className="auth-screen">
        <section className="auth-card">
          <h1>Support That Feels Instant.</h1>
          <p>
            Светлый цифровой интерфейс с живым чатом, где пользователь получает ответ от RAG или оператора.
          </p>
          <form className="auth-form" onSubmit={(event) => void submitAuth(event)}>
            <div className="split">
              <input
                value={login}
                onChange={(event) => setLogin(event.target.value)}
                placeholder="Login"
                autoComplete="username"
              />
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Password"
                autoComplete="current-password"
              />
            </div>

            {authMode === "register" && (
              <select value={authRole} onChange={(event) => setAuthRole(event.target.value as Role)}>
                <option value="registered_user">registered_user</option>
                <option value="operator">operator</option>
                <option value="admin">admin</option>
              </select>
            )}

            <div className="split">
              <button className="btn-primary" type="submit">
                {authMode === "register" ? "Register" : "Login"}
              </button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setAuthMode(authMode === "register" ? "login" : "register")}
              >
                {authMode === "register" ? "Switch To Login" : "Switch To Register"}
              </button>
            </div>
          </form>

          {notice && <div className={`notice ${noticeError ? "error" : ""}`}>{notice}</div>}
        </section>
      </div>
    );
  }

  const canUserCallOperator =
    profile.role === "registered_user" &&
    selectedChat &&
    selectedChat.userMessageCount > profile.operatorCallThresholdMessages &&
    !selectedChat.escalatedToOperator;

  return (
    <div className="app-shell">
      <aside className="panel sidebar">
        <div className="brand">
          <div>
            <div className="brand-title">FlashSupport</div>
            <div className="muted">{profile.login}</div>
          </div>
          <div className="role-chip">{friendlyRole(profile.role)}</div>
        </div>

        <div className="action-row">
          {profile.role === "registered_user" && (
            <button className="btn-primary" onClick={() => void createChat()}>
              New Chat
            </button>
          )}
          <button className="btn-ghost" onClick={() => void loadChats()}>
            Refresh
          </button>
          <button className="btn-secondary" onClick={() => void logout()}>
            Logout
          </button>
        </div>

        <div className="chat-list">
          {chats.map((chat) => (
            <button
              className={`chat-item ${chat.chatId === selectedChatId ? "active" : ""}`}
              key={chat.chatId}
              onClick={() => setSelectedChatId(chat.chatId)}
            >
              <h4>{chat.title}</h4>
              <p>{chat.preview || "No messages yet"}</p>
              <p>{chat.status}</p>
            </button>
          ))}
          {chats.length === 0 && <p className="muted">No chats available</p>}
        </div>
      </aside>

      <main className="panel main">
        <header className="header">
          <div>
            <h1>{selectedChat ? selectedChat.title : "Select A Chat"}</h1>
            <div className="muted">
              {selectedChat ? `status: ${selectedChat.status}` : "чат поддержки и role-based операции"}
            </div>
          </div>
        </header>

        <section className="messages">
          {messages.map((message) => (
            <div className={`msg ${message.senderRole === "registered_user" ? "user" : message.senderRole}`} key={message.messageId}>
              {message.text}
            </div>
          ))}
          {messages.length === 0 && <div className="muted">No messages in current chat</div>}
        </section>

        <footer>
          {profile.role !== "admin" ? (
            <div className="composer">
              <textarea
                value={messageText}
                onChange={(event) => setMessageText(event.target.value)}
                placeholder={profile.role === "registered_user" ? "Type your request" : "Type operator response"}
              />
              <button className="btn-primary" onClick={() => void sendMessage()}>
                Send
              </button>
            </div>
          ) : (
            <div className="notice">Admin mode: customer messaging is disabled by design.</div>
          )}

          <div className="action-row" style={{ marginTop: 10 }}>
            {canUserCallOperator && (
              <button className="btn-secondary" onClick={() => void callOperator()}>
                Call Operator
              </button>
            )}

            {profile.role === "operator" && selectedChatId && (
              <>
                <button className="btn-ghost" onClick={() => void runOperatorAction("resolve_chat")}>
                  Resolve
                </button>
                <button className="btn-ghost" onClick={() => void runOperatorAction("close_chat")}>
                  Close
                </button>
                <button className="btn-danger" onClick={() => void runOperatorAction("block_chat")}>
                  Block
                </button>
                <button className="btn-ghost" onClick={() => void deleteChat()}>
                  Delete Chat
                </button>
              </>
            )}
          </div>

          {notice && <div className={`notice ${noticeError ? "error" : ""}`}>{notice}</div>}
        </footer>
      </main>

      <section className="panel side-tools">
        {profile.role === "registered_user" && (
          <>
            <div className="card">
              <h3>How It Works</h3>
              <p>Сначала отвечает RAG, затем после порога сообщений можно вызвать оператора.</p>
              <p>
                Current threshold: <strong>{profile.operatorCallThresholdMessages}</strong>
              </p>
            </div>
            <div className="card">
              <h3>Chat Details</h3>
              <p>{selectedChat ? `Messages from user: ${selectedChat.userMessageCount}` : "Select chat"}</p>
              <p>{selectedChat ? `Escalated: ${selectedChat.escalatedToOperator ? "yes" : "no"}` : ""}</p>
            </div>
          </>
        )}

        {profile.role === "operator" && (
          <>
            <div className="card">
              <h3>RAG Assistant</h3>
              <input value={ragQuery} onChange={(event) => setRagQuery(event.target.value)} placeholder="Ask RAG" />
              <div className="action-row" style={{ marginTop: 10 }}>
                <button className="btn-primary" onClick={() => void searchRag()}>
                  Search
                </button>
              </div>
              <div style={{ marginTop: 12, display: "grid", gap: 8 }}>
                {ragResults.map((item, index) => (
                  <div className="card" key={index}>
                    <h4>{item.document_title ?? "Document"}</h4>
                    <p>{item.text ?? "No snippet"}</p>
                  </div>
                ))}
                {ragResults.length === 0 && <p className="muted">No RAG results yet</p>}
              </div>
            </div>

            <div className="card">
              <h3>Knowledge Draft</h3>
              <p>Оператор формирует Q/A заявку для проверки администратором.</p>
              <textarea
                value={knowledgeQuestion}
                onChange={(event) => setKnowledgeQuestion(event.target.value)}
                placeholder="Question"
              />
              <textarea
                value={knowledgeAnswer}
                onChange={(event) => setKnowledgeAnswer(event.target.value)}
                placeholder="Answer"
              />
              <div className="action-row">
                <button className="btn-primary" onClick={() => void submitKnowledgeRequest()}>
                  Send To Admin
                </button>
              </div>
            </div>
          </>
        )}

        {profile.role === "admin" && (
          <>
            <div className="card">
              <h3>Knowledge Review</h3>
              <div style={{ display: "grid", gap: 8 }}>
                {knowledgeRequests.map((request) => (
                  <div key={request.requestId} className="card">
                    <p>
                      <strong>Q:</strong> {request.question}
                    </p>
                    <p>
                      <strong>A:</strong> {request.answer}
                    </p>
                    <p>
                      status: {request.status} / dispatch: {request.dispatchStatus}
                    </p>
                    {request.status === "pending" && (
                      <div className="action-row">
                        <button className="btn-primary" onClick={() => void approveRequest(request.requestId)}>
                          Approve
                        </button>
                        <button className="btn-ghost" onClick={() => void rejectRequest(request.requestId)}>
                          Reject
                        </button>
                      </div>
                    )}
                  </div>
                ))}
                {knowledgeRequests.length === 0 && <p className="muted">No pending requests</p>}
              </div>
            </div>

            <div className="card">
              <h3>Account Control</h3>
              <div style={{ display: "grid", gap: 8 }}>
                {accounts.map((account) => (
                  <div key={account.userId} className="card">
                    <p>
                      <strong>{account.login}</strong> ({account.role})
                    </p>
                    <div className="action-row">
                      <button className="btn-ghost" onClick={() => void toggleBlock(account)}>
                        {account.isBlocked ? "Unblock" : "Block"}
                      </button>
                      <select
                        value={account.role}
                        onChange={(event) => void updateRole(account.userId, event.target.value as Role)}
                      >
                        <option value="registered_user">registered_user</option>
                        <option value="operator">operator</option>
                        <option value="admin">admin</option>
                      </select>
                    </div>
                  </div>
                ))}
                {accounts.length === 0 && <p className="muted">No known accounts yet</p>}
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

const root = document.getElementById("root");
if (!root) {
  throw new Error("Missing root container");
}

createRoot(root).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
