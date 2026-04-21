export type UserRole = "registered_user" | "operator" | "admin";

export type DeliveryRoute = "rag_engine" | "operator_queue";

export type ChatStatus =
  | "open"
  | "waiting_operator"
  | "in_progress_operator"
  | "closed"
  | "blocked"
  | "resolved"
  | "specialist_review";

export type OperatorAction = "close_chat" | "block_chat" | "resolve_chat" | "send_to_specialist_queue";

export interface ChatMessage {
  messageId: string;
  chatId: string;
  senderRole: UserRole | "assistant" | "system";
  senderId: string;
  text: string;
  createdAt: string;
}

export interface ChatThread {
  chatId: string;
  title: string;
  ownerUserId: string;
  status: ChatStatus;
  escalatedToOperator: boolean;
  assignedOperatorId: string | null;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
}

export interface ChatSummary {
  chatId: string;
  title: string;
  status: ChatStatus;
  escalatedToOperator: boolean;
  assignedOperatorId: string | null;
  updatedAt: string;
  preview: string;
  userMessageCount: number;
}

export type KnowledgeRequestStatus = "pending" | "approved" | "rejected";
export type KnowledgeDispatchStatus = "queued" | "sent";

export interface KnowledgeRequest {
  requestId: string;
  chatId: string;
  question: string;
  answer: string;
  createdBy: string;
  createdAt: string;
  status: KnowledgeRequestStatus;
  reviewedBy: string | null;
  reviewedAt: string | null;
  dispatchStatus: KnowledgeDispatchStatus;
}

export interface AccountRecord {
  userId: string;
  login: string;
  role: UserRole;
  isBlocked: boolean;
  updatedAt: string;
}
