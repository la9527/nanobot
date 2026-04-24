import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { NanobotClient } from "@/lib/nanobot-client";

interface ClientContextValue {
  client: NanobotClient;
  token: string;
  modelName: string | null;
  setModelName: (modelName: string | null) => void;
}

const ClientContext = createContext<ClientContextValue | null>(null);

export function ClientProvider({
  client,
  token,
  modelName = null,
  children,
}: {
  client: NanobotClient;
  token: string;
  modelName?: string | null;
  children: ReactNode;
}) {
  const [currentModelName, setCurrentModelName] = useState<string | null>(modelName);

  useEffect(() => {
    if (typeof modelName === "string") {
      const trimmed = modelName.trim();
      setCurrentModelName(trimmed || null);
      return;
    }
    setCurrentModelName(null);
  }, [modelName]);

  const setModelName = useCallback((value: string | null) => {
    if (typeof value === "string") {
      const trimmed = value.trim();
      setCurrentModelName(trimmed || null);
      return;
    }
    setCurrentModelName(null);
  }, []);

  const ctxValue = useMemo(
    () => ({
      client,
      token,
      modelName: currentModelName,
      setModelName,
    }),
    [client, token, currentModelName, setModelName],
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
