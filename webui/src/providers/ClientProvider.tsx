import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { NanobotClient } from "@/lib/nanobot-client";
import type { ModelTargetOption } from "@/lib/types";

interface ClientContextValue {
  client: NanobotClient;
  token: string;
  modelName: string | null;
  activeTarget: string | null;
  modelTargets: ModelTargetOption[];
  setModelName: (modelName: string | null) => void;
  setActiveTarget: (activeTarget: string | null) => void;
  resetModelSelection: () => void;
}

const ClientContext = createContext<ClientContextValue | null>(null);

export function ClientProvider({
  client,
  token,
  modelName = null,
  activeTarget = null,
  modelTargets = [],
  children,
}: {
  client: NanobotClient;
  token: string;
  modelName?: string | null;
  activeTarget?: string | null;
  modelTargets?: ModelTargetOption[];
  children: ReactNode;
}) {
  const [currentModelName, setCurrentModelName] = useState<string | null>(modelName);
  const [currentActiveTarget, setCurrentActiveTarget] = useState<string | null>(activeTarget);
  const defaultModelNameRef = useRef<string | null>(modelName);
  const defaultActiveTargetRef = useRef<string | null>(activeTarget);

  useEffect(() => {
    if (typeof modelName === "string") {
      const trimmed = modelName.trim();
      setCurrentModelName(trimmed || null);
      defaultModelNameRef.current = trimmed || null;
      return;
    }
    setCurrentModelName(null);
    defaultModelNameRef.current = null;
  }, [modelName]);

  useEffect(() => {
    if (typeof activeTarget === "string") {
      const trimmed = activeTarget.trim();
      setCurrentActiveTarget(trimmed || null);
      defaultActiveTargetRef.current = trimmed || null;
      return;
    }
    setCurrentActiveTarget(null);
    defaultActiveTargetRef.current = null;
  }, [activeTarget]);

  const setModelName = useCallback((value: string | null) => {
    if (typeof value === "string") {
      const trimmed = value.trim();
      setCurrentModelName(trimmed || null);
      return;
    }
    setCurrentModelName(null);
  }, []);

  const setActiveTarget = useCallback((value: string | null) => {
    if (typeof value === "string") {
      const trimmed = value.trim();
      setCurrentActiveTarget(trimmed || null);
      return;
    }
    setCurrentActiveTarget(null);
  }, []);

  const resetModelSelection = useCallback(() => {
    setCurrentModelName(defaultModelNameRef.current);
    setCurrentActiveTarget(defaultActiveTargetRef.current);
  }, []);

  const ctxValue = useMemo(
    () => ({
      client,
      token,
      modelName: currentModelName,
      activeTarget: currentActiveTarget,
      modelTargets,
      setModelName,
      setActiveTarget,
      resetModelSelection,
    }),
    [
      client,
      token,
      currentModelName,
      currentActiveTarget,
      modelTargets,
      setModelName,
      setActiveTarget,
      resetModelSelection,
    ],
  );

  return (
    <ClientContext.Provider value={ctxValue}>
      {children}
    </ClientContext.Provider>
  );
}

export function useClient(): ClientContextValue {
  const ctx = useContext(ClientContext);
  if (!ctx) {
    throw new Error("useClient must be used within a ClientProvider");
  }
  return ctx;
}
