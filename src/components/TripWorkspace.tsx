"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  A2UIProvider,
  A2UIRenderer,
  useA2UIActions,
} from "@copilotkit/a2ui-renderer";
import { useAgent } from "@copilotkit/react-core/v2";
import { catalog } from "@/a2ui/catalog";
import { surfaceBus } from "@/a2ui/surface-bus";
import { tripStore, type TripStop } from "@/a2ui/trip-store";
import { TripMap } from "./TripMap";
import { ItineraryPanel } from "./ItineraryPanel";

const CHANNEL = "trip_agent";

export function TripWorkspace() {
  const { agent } = useAgent({ agentId: CHANNEL });
  const [consumedId, setConsumedId] = useState<string | null>(null);
  const currentRef = useRef<string | null>(null);

  const handleSurfaceChange = useCallback((id: string | null) => {
    currentRef.current = id;
  }, []);

  const onAction = useCallback(
    (message: unknown) => {
      const ua = (
        message as {
          userAction?: { name?: string; context?: Record<string, unknown> };
        }
      )?.userAction;
      if (!ua?.name) return;

      // Replace the current card right away so it can't be clicked twice.
      setConsumedId(currentRef.current);

      const name = (ua.context?.name as string | undefined) ?? "this stop";
      let label = name;

      switch (ua.name) {
        case "approve_stop":
          if (ua.context) tripStore.addStop(ua.context as unknown as TripStop);
          label = `Added ${name}`;
          break;
        case "skip_stop":
          label = `Skip ${name}`;
          break;
        case "plan_more":
          label = "Plan another stop";
          break;
        case "restart_trip":
          tripStore.clear();
          label = "Start over";
          break;
        default:
          label = name;
      }

      agent.addMessage({
        id: crypto.randomUUID(),
        role: "user",
        content: label,
      });

      void agent
        .runAgent({ forwardedProps: { a2uiAction: message } })
        .catch((err) => console.warn("[trip-workspace] runAgent failed", err));
    },
    [agent],
  );

  return (
    <div className="h-full flex flex-col">
      {/* relative so the itinerary panel can overlay the map */}
      <div className="relative flex-1 min-h-0">
        <TripMap />
        <ItineraryPanel />
      </div>

      <div className="shrink-0 max-h-[44%] overflow-y-auto border-t border-[var(--line)] bg-[var(--surface)]">
        <A2UIProvider catalog={catalog} onAction={onAction}>
          <TripSurface
            consumedId={consumedId}
            onSurfaceChange={handleSurfaceChange}
          />
        </A2UIProvider>
      </div>
    </div>
  );
}

function TripSurface({
  consumedId,
  onSurfaceChange,
}: {
  consumedId: string | null;
  onSurfaceChange: (id: string | null) => void;
}) {
  const actions = useA2UIActions();
  const [surfaceId, setSurfaceId] = useState<string | null>(null);
  const seenRef = useRef(0);
  const createdRef = useRef<Set<string>>(new Set());

  function applyOps(ops: Array<Record<string, unknown>>) {
    if (!ops.length) return;
    const out = ops.filter((op) => {
      const cs = op.createSurface as { surfaceId?: string } | undefined;
      if (cs?.surfaceId) {
        if (createdRef.current.has(cs.surfaceId)) return false;
        createdRef.current.add(cs.surfaceId);
      }
      return true;
    });
    try {
      actions.processMessages(out);
    } catch (err) {
      console.warn("[trip-surface] processMessages threw:", err);
    }
  }

  useEffect(() => {
    const initial = surfaceBus.snapshot(CHANNEL);
    if (initial.ops.length) {
      applyOps(initial.ops as Array<Record<string, unknown>>);
      seenRef.current = initial.ops.length;
      setSurfaceId(initial.surfaceId);
    }
    return surfaceBus.subscribe(CHANNEL, (snap) => {
      const tail = snap.ops.slice(seenRef.current);
      if (tail.length) applyOps(tail as Array<Record<string, unknown>>);
      seenRef.current = snap.ops.length;
      if (snap.surfaceId) setSurfaceId(snap.surfaceId);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actions]);

  useEffect(() => {
    onSurfaceChange(surfaceId);
  }, [surfaceId, onSurfaceChange]);

  if (!surfaceId) {
    return (
      <div className="p-6 text-center text-[13px] text-[var(--ink)]/70">
        <p className="mono uppercase tracking-[0.14em] text-[11px]">
          waiting for Atlas
        </p>
        <p className="mt-1">
          Tell Atlas where you&rsquo;re going — proposed stops appear here to
          approve.
        </p>
      </div>
    );
  }

  if (surfaceId === consumedId) {
    return (
      <div className="p-6 flex items-center gap-3 text-[13px] text-[var(--ink)]/70">
        <span className="relative inline-flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--lilac)] opacity-75 animate-ping" />
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[var(--lilac)]" />
        </span>
        <span>Atlas is thinking&hellip;</span>
      </div>
    );
  }

  return (
    <div className="a2ui-surface p-5">
      <A2UIRenderer surfaceId={surfaceId} />
    </div>
  );
}
