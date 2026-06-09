import type { Metadata } from "next";
import { AgentWorkspace } from "@/components/features/agent/agent-workspace";

export const metadata: Metadata = {
  title: "AI Agent | Autonomous Drones",
  description: "Workspace hỏi AI Agent cho Autonomous Drones.",
};

export default function AgentPage() {
  return <AgentWorkspace />;
}
