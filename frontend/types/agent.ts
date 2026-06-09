export type AgentAskRequest = {
  question: string;
};

export type AgentResponse = {
  answer: string;
};

export type ChatSession = {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
};

export type ChatMessage = {
  id: number;
  role: "user" | "assistant" | "system" | "tool";
  message: string;
  timestamp: string;
};

export type ChatDetail = ChatSession & {
  messages: ChatMessage[];
};

export type ChatMessageResponse = {
  chat: ChatSession;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
};
