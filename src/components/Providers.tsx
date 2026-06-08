"use client";

import { CopilotKit } from "@copilotkit/react-core/v2";
import { createMirrorActivityRenderer } from "@/a2ui/MirrorRenderer";

/* The trip agent sends A2UI surfaces via activity messages; the mirror
 * renderer forwards them to the page-level workspace canvas and leaves a
 * small pill in chat as the handoff breadcrumb. */
const RENDERERS = [createMirrorActivityRenderer("trip_agent")];

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <CopilotKit runtimeUrl="/api/copilotkit" renderActivityMessages={RENDERERS}>
      {children}
    </CopilotKit>
  );
}
