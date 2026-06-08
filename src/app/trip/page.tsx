"use client";

import { CopilotChat, useAgent } from "@copilotkit/react-core/v2";
import { Split } from "@/components/Split";
import { TripWorkspace } from "@/components/TripWorkspace";

const AGENT_ID = "trip_agent";

export default function TripPage() {
  // Ensures the agent thread is registered for this page.
  useAgent({ agentId: AGENT_ID });

  return (
    <div className="h-screen flex flex-col bg-[var(--bg)]">
      <header className="shrink-0 px-5 py-3 border-b border-[var(--line)] flex items-center gap-2">
        <span className="font-semibold tracking-tight text-[var(--ink)]">
          Atlas
        </span>
        <span className="mono text-[11px] uppercase tracking-[0.14em] text-[var(--ink)]/60">
          trip architect · A2UI
        </span>
      </header>

      <Split
        persistKey="trip.split"
        initialLeftFraction={0.34}
        left={
          <div className="h-full copilot-chat-wrapper">
            <CopilotChat
              agentId={AGENT_ID}
              labels={{
                chatInputPlaceholder: "Where are we going?",
                welcomeMessageText:
                  "Tell me the place, how many days, your pace, and what you love — I'll plan it one stop at a time.",
              }}
            />
          </div>
        }
        right={<TripWorkspace />}
      />
    </div>
  );
}
