import {
  CopilotRuntime,
  createCopilotRuntimeHandler,
} from "@copilotkit/runtime/v2";
import { HttpAgent } from "@ag-ui/client";

const TRIP_AGENT_URL =
  process.env.TRIP_AGENT_URL ?? "http://localhost:8123/trip";

const tripAgent = new HttpAgent({ url: TRIP_AGENT_URL });

const runtime = new CopilotRuntime({
  agents: {
    // V2 hooks that don't pass an explicit agentId fall back to "default".
    default: tripAgent,
    trip_agent: tripAgent,
  },
  // The Python agent emits the A2UI ops itself; don't inject a frontend tool.
  a2ui: { injectA2UITool: false },
});

const handler = createCopilotRuntimeHandler({
  runtime,
  basePath: "/api/copilotkit",
  mode: "single-route",
});

export { handler as POST };
