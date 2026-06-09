import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { AgentWorkspace } from "@/components/features/agent/agent-workspace";

export const metadata: Metadata = {
  title: "AI Agent | Autonomous Drones",
  description: "Lịch sử trò chuyện với AI Agent cho Autonomous Drones.",
};

type AgentChatPageProps = {
  params: Promise<{
    chatId: string;
  }>;
};

export default async function AgentChatPage({ params }: AgentChatPageProps) {
  const { chatId: chatIdParam } = await params;
  const chatId = Number(chatIdParam);

  if (!Number.isSafeInteger(chatId) || chatId <= 0) {
    notFound();
  }

  return <AgentWorkspace chatId={chatId} />;
}
