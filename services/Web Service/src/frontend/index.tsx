import React, { FormEvent, useEffect, useMemo, useRef, useState } from "react";
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

type WebEvent =
  | {
      type: "connected";
      profile: Profile;
      chats: ChatSummary[];
    }
  | {
      type: "chat_updated";
      chat: ChatSummary;
      messages: ChatMessage[];
    }
  | {
      type: "chat_deleted";
      chatId: string;
    };

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

interface RuntimeDownloadStatus {
  status: string;
  model_name: string | null;
  huggingface_url: string | null;
  downloaded_bytes: number;
  total_bytes: number;
  progress_percent: number;
  eta_seconds: number | null;
  started_at: string | null;
  updated_at: string | null;
  error: string | null;
  local_file: string | null;
}

interface RuntimeModelInfo {
  model_name: string;
  active: boolean;
  source: string;
  local_file: string | null;
  model_format: string;
  backend: string;
  runnable: boolean;
}

interface RuntimeModelsPayload {
  active_model: string;
  device?: string;
  device_warning?: string | null;
  models: RuntimeModelInfo[];
  download: RuntimeDownloadStatus;
}

interface RuntimeSettingsPayload {
  system_prompt: string;
}

interface AppSettingsPayload {
  operator_call_threshold_messages: number;
}

interface EmbeddingDownloadStatus {
  status: string;
  model_name: string | null;
  huggingface_url: string | null;
  downloaded_bytes: number;
  total_bytes: number;
  progress_percent: number;
  started_at: string | null;
  updated_at: string | null;
  error: string | null;
  local_path: string | null;
}

interface EmbeddingModelInfo {
  model_name: string;
  active: boolean;
  source: string;
  repo_id: string;
  local_path: string;
  embedding_dimension: number;
  device: string;
  device_warning?: string | null;
  created_at: string | null;
}

interface EmbeddingModelsPayload {
  active_model: string | null;
  active_dimension: number | null;
  device?: string;
  device_warning?: string | null;
  models: EmbeddingModelInfo[];
  download: EmbeddingDownloadStatus;
}

interface RagSettingsPayload {
  chunk_size_chars: number;
  chunk_overlap_chars: number;
  top_k?: number;
}

interface KnowledgeBaseRecord {
  id: number;
  name: string;
  description: string | null;
  embedding_model: string;
  embedding_dimension: number;
  is_active: boolean;
  document_count: number;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

interface KnowledgeDocumentRecord {
  id: number;
  knowledge_base_id: number;
  title: string;
  source: string | null;
  chunk_count: number;
  created_at: string;
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

function sortChats(chats: ChatSummary[]): ChatSummary[] {
  return [...chats].sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
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

function compactWords(text: string, maxWords: number): string {
  return text.trim().split(/\s+/).filter(Boolean).slice(0, maxWords).join(" ");
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
  const selectedChatIdRef = useRef<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [messageText, setMessageText] = useState("");
  const [chatActivity, setChatActivity] = useState<{ chatId: string; label: string } | null>(null);

  const [ragQuery, setRagQuery] = useState("");
  const [ragResults, setRagResults] = useState<RagResult[]>([]);

  const [knowledgeQuestion, setKnowledgeQuestion] = useState("");
  const [knowledgeAnswer, setKnowledgeAnswer] = useState("");

  const [knowledgeRequests, setKnowledgeRequests] = useState<KnowledgeRequest[]>([]);
  const [accounts, setAccounts] = useState<AccountRecord[]>([]);
  const [operatorThresholdSetting, setOperatorThresholdSetting] = useState("5");
  const [runtimeModels, setRuntimeModels] = useState<RuntimeModelInfo[]>([]);
  const [activeRuntimeModel, setActiveRuntimeModel] = useState<string>("");
  const [runtimeDevice, setRuntimeDevice] = useState<string>("auto");
  const [runtimeDeviceWarning, setRuntimeDeviceWarning] = useState<string | null>(null);
  const [runtimeDownload, setRuntimeDownload] = useState<RuntimeDownloadStatus | null>(null);
  const [llmSystemPrompt, setLlmSystemPrompt] = useState("");
  const [huggingfaceUrl, setHuggingfaceUrl] = useState("");
  const [huggingfaceToken, setHuggingfaceToken] = useState("");
  const [runtimeModelName, setRuntimeModelName] = useState("");
  const [embeddingModels, setEmbeddingModels] = useState<EmbeddingModelInfo[]>([]);
  const [activeEmbeddingModel, setActiveEmbeddingModel] = useState<string>("");
  const [embeddingDevice, setEmbeddingDevice] = useState<string>("cpu");
  const [embeddingDeviceWarning, setEmbeddingDeviceWarning] = useState<string | null>(null);
  const [embeddingDownload, setEmbeddingDownload] = useState<EmbeddingDownloadStatus | null>(null);
  const [ragChunkSize, setRagChunkSize] = useState("1200");
  const [ragChunkOverlap, setRagChunkOverlap] = useState("160");
  const [ragTopK, setRagTopK] = useState("3");
  const [embeddingHuggingfaceUrl, setEmbeddingHuggingfaceUrl] = useState("");
  const [embeddingModelName, setEmbeddingModelName] = useState("");
  const [embeddingToken, setEmbeddingToken] = useState("");
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseRecord[]>([]);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<number | null>(null);
  const [knowledgeDocuments, setKnowledgeDocuments] = useState<KnowledgeDocumentRecord[]>([]);
  const [knowledgeBaseName, setKnowledgeBaseName] = useState("");
  const [knowledgeBaseDescription, setKnowledgeBaseDescription] = useState("");
  const [knowledgeDocTitle, setKnowledgeDocTitle] = useState("");
  const [knowledgeDocText, setKnowledgeDocText] = useState("");
  const [deleteKnowledgePassword, setDeleteKnowledgePassword] = useState("");

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

  const loadChats = async (options: { silent?: boolean } = {}): Promise<void> => {
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
      if (!options.silent) {
        setErrorNotice((error as Error).message);
      }
    }
  };

  const loadMessages = async (chatId: string, options: { silent?: boolean } = {}): Promise<void> => {
    try {
      const payload = await api<{ messages: ChatMessage[] }>(`/api/chats/${chatId}/messages`);
      setMessages((current) => {
        const localOnly = current.filter(
          (message) =>
            message.chatId === chatId &&
            (message.messageId.startsWith("pending-") || message.messageId.startsWith("error-")),
        );
        if (localOnly.length === 0) {
          return payload.messages;
        }
        const serverIds = new Set(payload.messages.map((message) => message.messageId));
        return [...payload.messages, ...localOnly.filter((message) => !serverIds.has(message.messageId))];
      });
    } catch (error) {
      if (!options.silent) {
        setErrorNotice((error as Error).message);
      }
    }
  };

  const loadAdminData = async (): Promise<void> => {
    if (!profile || profile.role !== "admin") {
      setKnowledgeRequests([]);
      setAccounts([]);
      setOperatorThresholdSetting("5");
      setRuntimeModels([]);
      setActiveRuntimeModel("");
      setRuntimeDevice("auto");
      setRuntimeDeviceWarning(null);
      setRuntimeDownload(null);
      setLlmSystemPrompt("");
      setEmbeddingModels([]);
      setActiveEmbeddingModel("");
      setEmbeddingDevice("cpu");
      setEmbeddingDeviceWarning(null);
      setEmbeddingDownload(null);
      setRagChunkSize("1200");
      setRagChunkOverlap("160");
      setRagTopK("3");
      setKnowledgeBases([]);
      setKnowledgeDocuments([]);
      return;
    }

    try {
      const [requestsPayload, accountsPayload, appSettingsPayload] = await Promise.all([
        api<{ requests: KnowledgeRequest[] }>("/api/admin/knowledge-requests"),
        api<{ accounts: AccountRecord[] }>("/api/admin/accounts"),
        api<AppSettingsPayload>("/api/admin/app/settings"),
      ]);
      setKnowledgeRequests(requestsPayload.requests);
      setAccounts(accountsPayload.accounts);
      setOperatorThresholdSetting(String(appSettingsPayload.operator_call_threshold_messages));
    } catch (error) {
      setErrorNotice((error as Error).message);
    }

    try {
      const [runtimePayload, runtimeSettingsPayload] = await Promise.all([
        api<RuntimeModelsPayload>("/api/admin/llm/models"),
        api<RuntimeSettingsPayload>("/api/admin/llm/settings"),
      ]);
      setRuntimeModels(runtimePayload.models);
      setActiveRuntimeModel(runtimePayload.active_model);
      setRuntimeDevice(runtimePayload.device ?? "auto");
      setRuntimeDeviceWarning(runtimePayload.device_warning ?? null);
      setRuntimeDownload(runtimePayload.download);
      setLlmSystemPrompt(runtimeSettingsPayload.system_prompt);
    } catch (error) {
      setRuntimeModels([]);
      setActiveRuntimeModel("");
      setRuntimeDevice("auto");
      setRuntimeDeviceWarning(null);
      setRuntimeDownload(null);
      setLlmSystemPrompt("");
      setErrorNotice((error as Error).message);
    }

    try {
      const [embeddingPayload, basesPayload, ragSettingsPayload] = await Promise.all([
        api<EmbeddingModelsPayload>("/api/admin/rag/embedding-models"),
        api<{ bases: KnowledgeBaseRecord[] }>("/api/admin/rag/knowledge-bases"),
        api<RagSettingsPayload>("/api/admin/rag/settings"),
      ]);
      setEmbeddingModels(embeddingPayload.models);
      setActiveEmbeddingModel(embeddingPayload.active_model ?? "");
      setEmbeddingDevice(embeddingPayload.device ?? "cpu");
      setEmbeddingDeviceWarning(embeddingPayload.device_warning ?? null);
      setEmbeddingDownload(embeddingPayload.download);
      setRagChunkSize(String(ragSettingsPayload.chunk_size_chars));
      setRagChunkOverlap(String(ragSettingsPayload.chunk_overlap_chars));
      setRagTopK(String(ragSettingsPayload.top_k ?? 3));
      setKnowledgeBases(basesPayload.bases);
      const activeBase = basesPayload.bases.find((item) => item.is_active) ?? basesPayload.bases[0] ?? null;
      setSelectedKnowledgeBaseId(activeBase?.id ?? null);
      if (activeBase) {
        const documentsPayload = await api<{ documents: KnowledgeDocumentRecord[] }>(
          `/api/admin/rag/knowledge-bases/${activeBase.id}/documents`,
        );
        setKnowledgeDocuments(documentsPayload.documents);
      } else {
        setKnowledgeDocuments([]);
      }
    } catch (error) {
      setEmbeddingModels([]);
      setActiveEmbeddingModel("");
      setEmbeddingDevice("cpu");
      setEmbeddingDeviceWarning(null);
      setEmbeddingDownload(null);
      setRagChunkSize("1200");
      setRagChunkOverlap("160");
      setRagTopK("3");
      setKnowledgeBases([]);
      setKnowledgeDocuments([]);
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
    selectedChatIdRef.current = selectedChatId;
  }, [selectedChatId]);

  useEffect(() => {
    if (!profile) {
      return;
    }

    const source = new EventSource("/api/events", { withCredentials: true });

    source.onmessage = (event: MessageEvent<string>) => {
      let payload: WebEvent;
      try {
        payload = JSON.parse(event.data) as WebEvent;
      } catch {
        return;
      }
      if (payload.type === "connected") {
        setProfile(payload.profile);
        setChats(payload.chats);
        const currentChatId = selectedChatIdRef.current;
        if (!currentChatId && payload.chats.length > 0) {
          setSelectedChatId(payload.chats[0].chatId);
        }
        return;
      }

      if (payload.type === "chat_updated") {
        const currentChatId = selectedChatIdRef.current;
        setChats((current) => {
          const withoutUpdated = current.filter((chat) => chat.chatId !== payload.chat.chatId);
          return sortChats([...withoutUpdated, payload.chat]);
        });
        if (!currentChatId) {
          setSelectedChatId(payload.chat.chatId);
        }
        if (!currentChatId || payload.chat.chatId === currentChatId) {
          setMessages(payload.messages);
        }
        return;
      }

      if (payload.type === "chat_deleted") {
        const currentChatId = selectedChatIdRef.current;
        setChats((current) => current.filter((chat) => chat.chatId !== payload.chatId));
        if (payload.chatId === currentChatId) {
          setSelectedChatId(null);
          setMessages([]);
        }
      }
    };

    source.onerror = () => {
      setErrorNotice("Realtime chat stream disconnected; reconnecting...");
    };

    return () => source.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.role]);

  useEffect(() => {
    if (!profile || profile.role !== "admin") {
      return;
    }
    if (!runtimeDownload || runtimeDownload.status !== "downloading") {
      return;
    }

    const interval = window.setInterval(() => {
      void loadLlmDownloadStatus();
    }, 1500);

    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.role, runtimeDownload?.status]);

  useEffect(() => {
    if (!profile || profile.role !== "admin") {
      return;
    }
    if (!embeddingDownload || embeddingDownload.status !== "downloading") {
      return;
    }

    const interval = window.setInterval(() => {
      void loadEmbeddingDownloadStatus();
    }, 1500);

    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.role, embeddingDownload?.status]);

  useEffect(() => {
    if (!profile || profile.role !== "admin" || !selectedKnowledgeBaseId) {
      setKnowledgeDocuments([]);
      return;
    }
    void loadKnowledgeDocuments(selectedKnowledgeBaseId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.role, selectedKnowledgeBaseId]);

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
    if (!profile) {
      setErrorNotice("Session is not active");
      return;
    }

    const textToSend = messageText.trim();
    if (textToSend === "") {
      setErrorNotice("Message cannot be empty");
      return;
    }

    let chatId = selectedChatId;
    if (!chatId) {
      if (profile.role === "registered_user") {
        try {
          const created = await api<{ chat: ChatSummary }>("/api/chats", {
            method: "POST",
            body: JSON.stringify({}),
          });
          chatId = created.chat.chatId;
          setSelectedChatId(chatId);
          await loadChats();
        } catch (error) {
          setErrorNotice((error as Error).message);
          return;
        }
      } else {
        setErrorNotice("Select a chat first");
        return;
      }
    }

    clearNotice();

    try {
      if (profile.role === "registered_user") {
        const pendingMessage: ChatMessage = {
          messageId: `pending-${Date.now()}`,
          chatId,
          senderRole: "registered_user",
          senderId: profile.userId,
          text: textToSend,
          createdAt: new Date().toISOString(),
        };
        setMessages((current) => {
          if (current.some((message) => message.messageId === pendingMessage.messageId)) {
            return current;
          }
          return [...current, pendingMessage];
        });
        setChats((current) =>
          current.map((chat) =>
            chat.chatId === chatId
              ? {
                  ...chat,
                  title: chat.userMessageCount === 0 ? compactWords(textToSend, 4) || chat.title : chat.title,
                  preview: compactWords(textToSend, 18),
                  userMessageCount: chat.userMessageCount + 1,
                }
              : chat,
          ),
        );
        setMessageText("");
        setChatActivity({ chatId, label: "RAG is thinking" });
        setNotice("Waiting for assistant response");

        const payload = await api<{ messages: ChatMessage[]; orchestratorMessage: string }>(
          `/api/chats/${chatId}/messages`,
          {
            method: "POST",
            body: JSON.stringify({ text: textToSend }),
          },
        );
        setMessages(payload.messages);
        setChatActivity(null);
        setNotice("Message sent");
      } else if (profile.role === "operator") {
        const pendingMessage: ChatMessage = {
          messageId: `pending-${Date.now()}`,
          chatId,
          senderRole: "operator",
          senderId: profile.userId,
          text: textToSend,
          createdAt: new Date().toISOString(),
        };
        setMessages((current) => [...current, pendingMessage]);
        setMessageText("");
        setChatActivity({ chatId, label: "Operator is sending" });
        const payload = await api<{ messages: ChatMessage[] }>(`/api/chats/${chatId}/operator-reply`, {
          method: "POST",
          body: JSON.stringify({ text: textToSend }),
        });
        setMessages(payload.messages);
        setChatActivity(null);
        setNotice("Operator response sent");
      } else {
        setErrorNotice("Admins do not communicate with customers directly");
        return;
      }

      await loadChats();
    } catch (error) {
      setChatActivity(null);
      if (profile.role === "registered_user") {
        setMessages((current) => [
          ...current,
          {
            messageId: `error-${Date.now()}`,
            chatId,
            senderRole: "system",
            senderId: "web-service",
            text: `Assistant response failed: ${(error as Error).message}`,
            createdAt: new Date().toISOString(),
          },
        ]);
      } else {
        setErrorNotice((error as Error).message);
      }
    }
  };

  const callOperator = async (): Promise<void> => {
    if (!selectedChatId) {
      setErrorNotice("Select a chat first");
      return;
    }

    clearNotice();

    try {
      setChatActivity({ chatId: selectedChatId, label: "Calling operator" });
      const payload = await api<{ messages: ChatMessage[] }>(`/api/chats/${selectedChatId}/call-operator`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setMessages(payload.messages);
      setChatActivity(null);
      await loadChats();
      setNotice("Operator call has been sent");
    } catch (error) {
      setChatActivity(null);
      setMessages((current) => [
        ...current,
        {
          messageId: `error-${Date.now()}`,
          chatId: selectedChatId,
          senderRole: "system",
          senderId: "web-service",
          text: `Operator call failed: ${(error as Error).message}`,
          createdAt: new Date().toISOString(),
        },
      ]);
    }
  };

  const runOperatorAction = async (action: "close_chat" | "block_chat" | "resolve_chat" | "send_to_specialist_queue") => {
    if (!selectedChatId) {
      setErrorNotice("Select a chat first");
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
      setErrorNotice("Select a chat first");
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
      setErrorNotice("Search query cannot be empty");
      return;
    }

    clearNotice();

    try {
      const topK = Number(ragTopK);
      const payload = await api<{ results: RagResult[] }>("/api/rag/search", {
        method: "POST",
        body: JSON.stringify({ query: ragQuery, top_k: Number.isInteger(topK) ? topK : 3 }),
      });
      setRagResults(payload.results);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const submitKnowledgeRequest = async (): Promise<void> => {
    clearNotice();

    try {
      await api<KnowledgeRequest>("/api/operator/knowledge-requests", {
        method: "POST",
        body: JSON.stringify({
          chat_id: selectedChatId ?? null,
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

  const saveOperatorThreshold = async (): Promise<void> => {
    if (!profile || profile.role !== "admin") {
      setErrorNotice("Only admin can update app settings");
      return;
    }
    const threshold = Number(operatorThresholdSetting);
    if (!Number.isInteger(threshold) || threshold < 0 || threshold > 100) {
      setErrorNotice("Operator threshold must be an integer in range [0, 100]");
      return;
    }

    clearNotice();
    try {
      const payload = await api<AppSettingsPayload>("/api/admin/app/settings", {
        method: "POST",
        body: JSON.stringify({ operator_call_threshold_messages: threshold }),
      });
      setOperatorThresholdSetting(String(payload.operator_call_threshold_messages));
      setNotice("Operator threshold updated");
      setNoticeError(false);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const loadLlmDownloadStatus = async (): Promise<void> => {
    if (!profile || profile.role !== "admin") {
      return;
    }
    try {
      const payload = await api<RuntimeDownloadStatus>("/api/admin/llm/models/download-status");
      setRuntimeDownload(payload);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const startLlmModelDownload = async (): Promise<void> => {
    if (!profile || profile.role !== "admin") {
      setErrorNotice("Only admin can download runtime models");
      return;
    }
    if (!huggingfaceUrl.trim()) {
      setErrorNotice("Hugging Face URL cannot be empty");
      return;
    }

    clearNotice();
    try {
      const payload = await api<RuntimeDownloadStatus>("/api/admin/llm/models/download", {
        method: "POST",
        body: JSON.stringify({
          huggingface_url: huggingfaceUrl,
          huggingface_token: huggingfaceToken || null,
          model_name: runtimeModelName || null,
        }),
      });
      setRuntimeDownload(payload);
      setNotice("Model download started");
      setNoticeError(false);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const activateLlmModel = async (modelName: string): Promise<void> => {
    if (!profile || profile.role !== "admin") {
      setErrorNotice("Only admin can switch runtime models");
      return;
    }

    clearNotice();
    try {
      const payload = await api<RuntimeModelsPayload>("/api/admin/llm/models/activate", {
        method: "POST",
        body: JSON.stringify({ model_name: modelName }),
      });
      setRuntimeModels(payload.models);
      setActiveRuntimeModel(payload.active_model);
      setRuntimeDevice(payload.device ?? "auto");
      setRuntimeDeviceWarning(payload.device_warning ?? null);
      setRuntimeDownload(payload.download);
      setNotice(`Active LLM model switched to '${payload.active_model}'`);
      setNoticeError(false);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const saveLlmSystemPrompt = async (): Promise<void> => {
    if (!profile || profile.role !== "admin") {
      setErrorNotice("Only admin can update LLM settings");
      return;
    }
    if (!llmSystemPrompt.trim()) {
      setErrorNotice("System prompt cannot be empty");
      return;
    }

    clearNotice();
    try {
      const payload = await api<RuntimeSettingsPayload>("/api/admin/llm/settings", {
        method: "POST",
        body: JSON.stringify({ system_prompt: llmSystemPrompt }),
      });
      setLlmSystemPrompt(payload.system_prompt);
      setNotice("LLM system prompt updated");
      setNoticeError(false);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const loadEmbeddingDownloadStatus = async (): Promise<void> => {
    if (!profile || profile.role !== "admin") {
      return;
    }
    try {
      const payload = await api<EmbeddingDownloadStatus>("/api/admin/rag/embedding-models/download-status");
      setEmbeddingDownload(payload);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const startEmbeddingModelDownload = async (): Promise<void> => {
    if (!profile || profile.role !== "admin") {
      setErrorNotice("Only admin can download embedding models");
      return;
    }
    if (!embeddingHuggingfaceUrl.trim()) {
      setErrorNotice("Embedding model Hugging Face URL cannot be empty");
      return;
    }

    clearNotice();
    try {
      const payload = await api<EmbeddingDownloadStatus>("/api/admin/rag/embedding-models/download", {
        method: "POST",
        body: JSON.stringify({
          huggingface_url: embeddingHuggingfaceUrl,
          huggingface_token: embeddingToken || null,
          model_name: embeddingModelName || null,
        }),
      });
      setEmbeddingDownload(payload);
      setNotice("Embedding model download started");
      setNoticeError(false);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const activateEmbeddingModel = async (modelName: string): Promise<void> => {
    clearNotice();
    try {
      const payload = await api<EmbeddingModelsPayload>("/api/admin/rag/embedding-models/activate", {
        method: "POST",
        body: JSON.stringify({ model_name: modelName }),
      });
      setEmbeddingModels(payload.models);
      setActiveEmbeddingModel(payload.active_model ?? "");
      setEmbeddingDevice(payload.device ?? "cpu");
      setEmbeddingDeviceWarning(payload.device_warning ?? null);
      setEmbeddingDownload(payload.download);
      setNotice(`Active embedding model switched to '${payload.active_model ?? "not set"}'`);
      setNoticeError(false);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const saveRagSettings = async (): Promise<void> => {
    if (!profile || profile.role !== "admin") {
      setErrorNotice("Only admin can update RAG settings");
      return;
    }
    const chunkSize = Number(ragChunkSize);
    const chunkOverlap = Number(ragChunkOverlap);
    const topK = Number(ragTopK);
    if (!Number.isInteger(chunkSize) || chunkSize < 200 || chunkSize > 8000) {
      setErrorNotice("Chunk size must be an integer in range [200, 8000]");
      return;
    }
    if (!Number.isInteger(chunkOverlap) || chunkOverlap < 0 || chunkOverlap > 2000) {
      setErrorNotice("Chunk overlap must be an integer in range [0, 2000]");
      return;
    }
    if (chunkOverlap >= chunkSize) {
      setErrorNotice("Chunk overlap must be smaller than chunk size");
      return;
    }
    if (!Number.isInteger(topK) || topK < 1 || topK > 50) {
      setErrorNotice("Top-K must be an integer in range [1, 50]");
      return;
    }

    clearNotice();
    try {
      const payload = await api<RagSettingsPayload>("/api/admin/rag/settings", {
        method: "POST",
        body: JSON.stringify({
          chunk_size_chars: chunkSize,
          chunk_overlap_chars: chunkOverlap,
          top_k: topK,
        }),
      });
      setRagChunkSize(String(payload.chunk_size_chars));
      setRagChunkOverlap(String(payload.chunk_overlap_chars));
      setRagTopK(String(payload.top_k ?? topK));
      setNotice("RAG chunk settings updated");
      setNoticeError(false);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const loadKnowledgeDocuments = async (knowledgeBaseId: number): Promise<void> => {
    try {
      const payload = await api<{ documents: KnowledgeDocumentRecord[] }>(
        `/api/admin/rag/knowledge-bases/${knowledgeBaseId}/documents`,
      );
      setKnowledgeDocuments(payload.documents);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const createKnowledgeBase = async (): Promise<void> => {
    if (!knowledgeBaseName.trim()) {
      setErrorNotice("Knowledge base name cannot be empty");
      return;
    }
    if (!knowledgeDocText.trim()) {
      setErrorNotice("Document text is required");
      return;
    }

    clearNotice();
    try {
      const base = await api<KnowledgeBaseRecord>("/api/admin/rag/knowledge-bases", {
        method: "POST",
        body: JSON.stringify({
          name: knowledgeBaseName,
          description: knowledgeBaseDescription || null,
          documents: [
            {
              title: knowledgeDocTitle.trim() || "Untitled document",
              text: knowledgeDocText,
            },
          ],
        }),
      });
      setSelectedKnowledgeBaseId(base.id);
      setKnowledgeBaseName("");
      setKnowledgeBaseDescription("");
      setKnowledgeDocTitle("");
      setKnowledgeDocText("");
      await loadAdminData();
      setNotice(`Knowledge base '${base.name}' created`);
      setNoticeError(false);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const addKnowledgeDocument = async (): Promise<void> => {
    if (!selectedKnowledgeBaseId) {
      setErrorNotice("Select a knowledge base first");
      return;
    }
    if (!knowledgeDocText.trim()) {
      setErrorNotice("Document text is required");
      return;
    }

    clearNotice();
    try {
      await api<KnowledgeDocumentRecord>(`/api/admin/rag/knowledge-bases/${selectedKnowledgeBaseId}/documents`, {
        method: "POST",
        body: JSON.stringify({
          title: knowledgeDocTitle.trim() || "Untitled document",
          text: knowledgeDocText,
        }),
      });
      setKnowledgeDocTitle("");
      setKnowledgeDocText("");
      await loadAdminData();
      setNotice("Document added to knowledge base");
      setNoticeError(false);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const activateKnowledgeBase = async (knowledgeBaseId: number): Promise<void> => {
    clearNotice();
    try {
      await api<KnowledgeBaseRecord>(`/api/admin/rag/knowledge-bases/${knowledgeBaseId}/activate`, {
        method: "POST",
      });
      setSelectedKnowledgeBaseId(knowledgeBaseId);
      await loadAdminData();
      setNotice("Active RAG knowledge base switched");
      setNoticeError(false);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const deleteKnowledgeBase = async (): Promise<void> => {
    if (!selectedKnowledgeBaseId) {
      setErrorNotice("Select a knowledge base first");
      return;
    }
    if (!deleteKnowledgePassword) {
      setErrorNotice("Admin password is required to delete a knowledge base");
      return;
    }

    clearNotice();
    try {
      await api<void>(`/api/admin/rag/knowledge-bases/${selectedKnowledgeBaseId}`, {
        method: "DELETE",
        body: JSON.stringify({ admin_password: deleteKnowledgePassword }),
      });
      setDeleteKnowledgePassword("");
      setSelectedKnowledgeBaseId(null);
      await loadAdminData();
      setNotice("Knowledge base deleted");
      setNoticeError(false);
    } catch (error) {
      setErrorNotice((error as Error).message);
    }
  };

  const deleteKnowledgeDocument = async (documentId: number): Promise<void> => {
    if (!selectedKnowledgeBaseId) {
      return;
    }
    clearNotice();
    try {
      await api<void>(`/api/admin/rag/knowledge-bases/${selectedKnowledgeBaseId}/documents/${documentId}`, {
        method: "DELETE",
      });
      await loadKnowledgeDocuments(selectedKnowledgeBaseId);
      await loadAdminData();
      setNotice("Document deleted");
      setNoticeError(false);
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
    selectedChat.status !== "closed" &&
    selectedChat.status !== "blocked" &&
    (selectedChat.userMessageCount > profile.operatorCallThresholdMessages ||
      selectedChat.assignedOperatorId !== null ||
      selectedChat.status === "resolved") &&
    !selectedChat.escalatedToOperator;

  const formatBytes = (bytes: number): string => {
    if (!Number.isFinite(bytes) || bytes <= 0) {
      return "0 B";
    }
    const units = ["B", "KB", "MB", "GB", "TB"];
    let value = bytes;
    let index = 0;
    while (value >= 1024 && index < units.length - 1) {
      value /= 1024;
      index += 1;
    }
    return `${value.toFixed(value >= 100 || index === 0 ? 0 : 1)} ${units[index]}`;
  };

  const formatEta = (etaSeconds: number | null): string => {
    if (etaSeconds === null || etaSeconds < 0) {
      return "unknown";
    }
    const hours = Math.floor(etaSeconds / 3600);
    const minutes = Math.floor((etaSeconds % 3600) / 60);
    const seconds = etaSeconds % 60;
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    }
    if (minutes > 0) {
      return `${minutes}m ${seconds}s`;
    }
    return `${seconds}s`;
  };

  return (
    <div className={`app-shell ${profile.role === "admin" ? "admin-shell" : ""}`}>
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

      <main className={`panel main ${profile.role === "admin" ? "admin-chat-panel" : ""}`}>
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
          {chatActivity?.chatId === selectedChatId && (
            <div className="msg assistant typing-msg">
              <span>{chatActivity.label}</span>
              <span className="typing-dots" aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
            </div>
          )}
          {!chatActivity && selectedChat?.status === "waiting_operator" && (
            <div className="msg system typing-msg">
              <span>Waiting for operator</span>
              <span className="typing-dots" aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
            </div>
          )}
          {messages.length === 0 && chatActivity?.chatId !== selectedChatId && (
            <div className="muted">No messages in current chat</div>
          )}
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

      <section className={`panel side-tools ${profile.role === "admin" ? "admin-tools" : ""}`}>
        {profile.role === "registered_user" && (
          <>
            <div className="card admin-compact">
              <h3>How It Works</h3>
              <p>Сначала отвечает RAG, затем после порога сообщений можно вызвать оператора.</p>
              <p>
                Current threshold: <strong>{profile.operatorCallThresholdMessages}</strong>
              </p>
            </div>
            <div className="card admin-compact">
              <h3>Chat Details</h3>
              <p>{selectedChat ? `Messages from user: ${selectedChat.userMessageCount}` : "Select chat"}</p>
              <p>{selectedChat ? `Escalated: ${selectedChat.escalatedToOperator ? "yes" : "no"}` : ""}</p>
            </div>
          </>
        )}

        {profile.role === "operator" && (
          <>
            <div className="card admin-wide">
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

            <div className="card admin-wide">
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
            <details className="admin-section" open>
              <summary>
                Knowledge Review <span className="admin-meta">{knowledgeRequests.length} requests</span>
              </summary>
              <div className="admin-section-body">
                <div className="card admin-wide">
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
              </div>
            </details>

            <details className="admin-section" open>
              <summary>
                Account Control <span className="admin-meta">{accounts.length} accounts</span>
              </summary>
              <div className="admin-section-body">
                <div className="card admin-compact">
              <h3>Account Control</h3>
              <div className="action-row" style={{ marginBottom: 12 }}>
                <input
                  value={operatorThresholdSetting}
                  onChange={(event) => setOperatorThresholdSetting(event.target.value)}
                  placeholder="Operator call threshold"
                  type="number"
                  min={0}
                  max={100}
                />
                <button className="btn-ghost" onClick={() => void saveOperatorThreshold()}>
                  Save Threshold
                </button>
              </div>
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
              </div>
            </details>

            <details className="admin-section" open>
              <summary>
                LLM Runtime <span className="admin-meta">{activeRuntimeModel || "not set"}</span>
              </summary>
              <div className="admin-section-body">
                <div className="card admin-wide">
              <h3>LLM Runtime Models</h3>
              <p>Скачивание модели из Hugging Face и переключение активной модели в реальном времени.</p>
              <p className="muted">
                Поддерживаются форматы: <code>.gguf</code>, <code>.safetensors</code>, <code>.bin</code>,{" "}
                <code>.pt</code>, <code>.pth</code>, <code>.onnx</code>, <code>.ggml</code>. Активировать в Ollama
                можно только <code>.gguf</code>, остальные сохраняются как download-only.
              </p>
              <textarea
                value={llmSystemPrompt}
                onChange={(event) => setLlmSystemPrompt(event.target.value)}
                placeholder="LLM system prompt for generated answers"
                rows={5}
              />
              <div className="action-row" style={{ marginTop: 8 }}>
                <button className="btn-ghost" onClick={() => void saveLlmSystemPrompt()}>
                  Save System Prompt
                </button>
              </div>
              <input
                value={huggingfaceUrl}
                onChange={(event) => setHuggingfaceUrl(event.target.value)}
                placeholder="Hugging Face URL (repo or file)"
              />
              <input
                value={runtimeModelName}
                onChange={(event) => setRuntimeModelName(event.target.value)}
                placeholder="Runtime model name (optional)"
              />
              <input
                value={huggingfaceToken}
                onChange={(event) => setHuggingfaceToken(event.target.value)}
                placeholder="Hugging Face token (optional)"
                type="password"
              />
              <div className="action-row" style={{ marginTop: 8 }}>
                <button className="btn-primary" onClick={() => void startLlmModelDownload()}>
                  Download Model
                </button>
                <button className="btn-ghost" onClick={() => void loadAdminData()}>
                  Refresh Models
                </button>
              </div>

              <div style={{ marginTop: 12 }}>
                <p>
                  Download status: <strong>{runtimeDownload?.status ?? "idle"}</strong>
                </p>
                <p>
                  Progress:{" "}
                  <strong>
                    {runtimeDownload ? `${runtimeDownload.progress_percent.toFixed(1)}%` : "0.0%"}
                  </strong>
                </p>
                <p>
                  Downloaded:{" "}
                  <strong>
                    {formatBytes(runtimeDownload?.downloaded_bytes ?? 0)} / {formatBytes(runtimeDownload?.total_bytes ?? 0)}
                  </strong>
                </p>
                <p>
                  ETA: <strong>{formatEta(runtimeDownload?.eta_seconds ?? null)}</strong>
                </p>
                {runtimeDownload?.error && <p className="notice error">{runtimeDownload.error}</p>}
              </div>

              <div style={{ marginTop: 12, display: "grid", gap: 8 }}>
                <p>
                  Active model: <strong>{activeRuntimeModel || "not set"}</strong>
                </p>
                <p>
                  Device mode: <strong>{runtimeDevice}</strong>
                </p>
                {runtimeDeviceWarning && <p className="notice error">{runtimeDeviceWarning}</p>}
                {runtimeModels.map((model) => (
                  <div key={model.model_name} className="card">
                    <p>
                      <strong>{model.model_name}</strong> ({model.source})
                    </p>
                    <p>
                      format: {model.model_format} / backend: {model.backend} / mode:{" "}
                      {model.runnable ? "runnable" : "download-only"}
                    </p>
                    <p>{model.local_file ? model.local_file : "local file: n/a"}</p>
                    <div className="action-row">
                      <button
                        className="btn-ghost"
                        onClick={() => void activateLlmModel(model.model_name)}
                        disabled={model.active || !model.runnable}
                      >
                        {model.active ? "Active" : model.runnable ? "Activate" : "Unavailable"}
                      </button>
                    </div>
                  </div>
                ))}
                {runtimeModels.length === 0 && <p className="muted">No runtime models available</p>}
              </div>
                </div>
              </div>
            </details>

            <details className="admin-section">
              <summary>
                Embedding Models <span className="admin-meta">{activeEmbeddingModel || "not set"}</span>
              </summary>
              <div className="admin-section-body">
                <div className="card admin-wide">
              <h3>RAG Embedding Models</h3>
              <input
                value={embeddingHuggingfaceUrl}
                onChange={(event) => setEmbeddingHuggingfaceUrl(event.target.value)}
                placeholder="Hugging Face repo, e.g. sentence-transformers/all-MiniLM-L6-v2"
              />
              <input
                value={embeddingModelName}
                onChange={(event) => setEmbeddingModelName(event.target.value)}
                placeholder="Embedding model name (optional)"
              />
              <input
                value={embeddingToken}
                onChange={(event) => setEmbeddingToken(event.target.value)}
                placeholder="Hugging Face token (optional)"
                type="password"
              />
              <div className="action-row" style={{ marginTop: 8 }}>
                <button className="btn-primary" onClick={() => void startEmbeddingModelDownload()}>
                  Download Embedding Model
                </button>
                <button className="btn-ghost" onClick={() => void loadAdminData()}>
                  Refresh RAG
                </button>
              </div>
              <div style={{ marginTop: 12 }}>
                <p>
                  Download status: <strong>{embeddingDownload?.status ?? "idle"}</strong>
                </p>
                <p>
                  Progress:{" "}
                  <strong>
                    {embeddingDownload ? `${embeddingDownload.progress_percent.toFixed(1)}%` : "0.0%"}
                  </strong>
                </p>
                {embeddingDownload?.error && <p className="notice error">{embeddingDownload.error}</p>}
              </div>
              <div style={{ marginTop: 12, display: "grid", gap: 8 }}>
                <p>
                  Active embedding model: <strong>{activeEmbeddingModel || "not set"}</strong>
                </p>
                <p>
                  Embedding device: <strong>{embeddingDevice}</strong>
                </p>
                {embeddingDeviceWarning && <p className="notice error">{embeddingDeviceWarning}</p>}
                {embeddingModels.map((model) => (
                  <div key={model.model_name} className="card">
                    <p>
                      <strong>{model.model_name}</strong> ({model.source})
                    </p>
                    <p>
                      repo: {model.repo_id} / dim: {model.embedding_dimension} / device: {model.device}
                    </p>
                    {model.device_warning && <p className="notice error">{model.device_warning}</p>}
                    <p>{model.local_path}</p>
                    <div className="action-row">
                      <button
                        className="btn-ghost"
                        onClick={() => void activateEmbeddingModel(model.model_name)}
                        disabled={model.active}
                      >
                        {model.active ? "Active" : "Activate"}
                      </button>
                    </div>
                  </div>
                ))}
                {embeddingModels.length === 0 && <p className="muted">No embedding models available</p>}
              </div>
                </div>
              </div>
            </details>

            <details className="admin-section" open>
              <summary>
                Knowledge Bases <span className="admin-meta">{knowledgeBases.length} bases</span>
              </summary>
              <div className="admin-section-body">
                <div className="card admin-wide">
              <h3>RAG Knowledge Bases</h3>
              <div className="action-row">
                <input
                  value={ragChunkSize}
                  onChange={(event) => setRagChunkSize(event.target.value)}
                  placeholder="Chunk window chars"
                  type="number"
                  min={200}
                  max={8000}
                />
                <input
                  value={ragChunkOverlap}
                  onChange={(event) => setRagChunkOverlap(event.target.value)}
                  placeholder="Chunk overlap chars"
                  type="number"
                  min={0}
                  max={2000}
                />
                <input
                  value={ragTopK}
                  onChange={(event) => setRagTopK(event.target.value)}
                  placeholder="Top-K chunks"
                  type="number"
                  min={1}
                  max={50}
                />
                <button className="btn-ghost" onClick={() => void saveRagSettings()}>
                  Save RAG Settings
                </button>
              </div>

              <div className="action-row">
                <select
                  value={selectedKnowledgeBaseId ?? ""}
                  onChange={(event) => setSelectedKnowledgeBaseId(event.target.value ? Number(event.target.value) : null)}
                >
                  <option value="">Select knowledge base</option>
                  {knowledgeBases.map((base) => (
                    <option key={base.id} value={base.id}>
                      {base.is_active ? "active: " : ""}
                      {base.name}
                    </option>
                  ))}
                </select>
                <button
                  className="btn-ghost"
                  disabled={!selectedKnowledgeBaseId}
                  onClick={() => selectedKnowledgeBaseId && void activateKnowledgeBase(selectedKnowledgeBaseId)}
                >
                  Activate
                </button>
              </div>

              <div className="kb-list">
                {knowledgeBases.map((base) => (
                  <div key={base.id} className="card">
                    <p>
                      <strong>{base.name}</strong> {base.is_active ? "(active)" : ""}
                    </p>
                    <p>
                      docs: {base.document_count} / chunks: {base.chunk_count} / model: {base.embedding_model} / dim:{" "}
                      {base.embedding_dimension}
                    </p>
                    {base.description && <p>{base.description}</p>}
                  </div>
                ))}
                {knowledgeBases.length === 0 && <p className="muted">No knowledge bases yet</p>}
              </div>

              <details className="admin-foldout">
                <summary>Create new base</summary>
                <div className="foldout-body">
                  <input
                    value={knowledgeBaseName}
                    onChange={(event) => setKnowledgeBaseName(event.target.value)}
                    placeholder="New knowledge base name"
                  />
                  <input
                    value={knowledgeBaseDescription}
                    onChange={(event) => setKnowledgeBaseDescription(event.target.value)}
                    placeholder="Description (optional)"
                  />
                  <button className="btn-primary" onClick={() => void createKnowledgeBase()}>
                    Create Base Using Document Below
                  </button>
                </div>
              </details>

              <div className="document-form">
                <h4>Add Document</h4>
                <input
                  value={knowledgeDocTitle}
                  onChange={(event) => setKnowledgeDocTitle(event.target.value)}
                  placeholder="Document title (optional)"
                />
                <textarea
                  value={knowledgeDocText}
                  onChange={(event) => setKnowledgeDocText(event.target.value)}
                  placeholder="Document JSON/text content for indexing"
                  rows={8}
                />
                <div className="action-row">
                  <button className="btn-primary" disabled={!selectedKnowledgeBaseId} onClick={() => void addKnowledgeDocument()}>
                    Add Document
                  </button>
                </div>
              </div>

              <div style={{ marginTop: 12, display: "grid", gap: 8 }}>
                <h4>Documents</h4>
                {knowledgeDocuments.map((document) => (
                  <div key={document.id} className="card">
                    <p>
                      <strong>{document.title}</strong>
                    </p>
                    <p>
                      chunks: {document.chunk_count} / source: {document.source ?? "n/a"}
                    </p>
                    <button className="btn-ghost" onClick={() => void deleteKnowledgeDocument(document.id)}>
                      Delete Document
                    </button>
                  </div>
                ))}
                {knowledgeDocuments.length === 0 && <p className="muted">No documents in selected base</p>}
              </div>

              <div style={{ marginTop: 12 }}>
                <input
                  value={deleteKnowledgePassword}
                  onChange={(event) => setDeleteKnowledgePassword(event.target.value)}
                  placeholder="Admin password to delete selected base"
                  type="password"
                />
                <button className="btn-ghost" disabled={!selectedKnowledgeBaseId} onClick={() => void deleteKnowledgeBase()}>
                  Delete Selected Base
                </button>
              </div>
                </div>
              </div>
            </details>
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
