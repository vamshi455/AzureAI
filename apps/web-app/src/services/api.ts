import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from "axios";
import {
  PublicClientApplication,
  type SilentRequest,
  type AccountInfo,
} from "@azure/msal-browser";

// --- Types ---
export interface KPIData {
  totalRevenue: number;
  revenueChange: number;
  totalOrders: number;
  ordersChange: number;
  productionOutput: number;
  productionChange: number;
  avgOrderValue: number;
  avgOrderValueChange: number;
}

export interface DemandForecast {
  period: string;
  actual: number;
  predicted: number;
  lower_bound: number;
  upper_bound: number;
}

export interface PipelineStatus {
  id: string;
  name: string;
  status: "succeeded" | "running" | "failed" | "queued";
  lastRunTime: string;
  duration: number;
  recordsProcessed: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  agentId?: string;
  citations?: Citation[];
  isStreaming?: boolean;
}

export interface Citation {
  title: string;
  source: string;
  url: string;
}

export interface ChatRequest {
  agent_id: string;
  messages: Array<{ role: string; content: string }>;
  stream?: boolean;
}

export interface Ticket {
  id: string;
  title: string;
  description?: string;
  status: string;
  priority: string;
  assignee?: string;
  labels?: string[];
  created_at: string;
  updated_at: string;
}

export interface CreateTicketPayload {
  title: string;
  description?: string;
  priority: string;
  labels?: string[];
}

// --- MSAL Configuration ---
const msalConfig = {
  auth: {
    clientId: import.meta.env.VITE_AZURE_CLIENT_ID || "00000000-0000-0000-0000-000000000000",
    authority: `https://login.microsoftonline.com/${import.meta.env.VITE_AZURE_TENANT_ID || "common"}`,
    redirectUri: import.meta.env.VITE_REDIRECT_URI || window.location.origin,
  },
  cache: {
    cacheLocation: "sessionStorage" as const,
    storeAuthStateInCookie: false,
  },
};

const msalInstance = new PublicClientApplication(msalConfig);

const API_SCOPES = [import.meta.env.VITE_API_SCOPE || "api://data-platform-api/.default"];

// --- Auth Helper ---
async function getAccessToken(): Promise<string | null> {
  const accounts: AccountInfo[] = msalInstance.getAllAccounts();
  if (accounts.length === 0) return null;

  const request: SilentRequest = {
    scopes: API_SCOPES,
    account: accounts[0],
  };

  try {
    const response = await msalInstance.acquireTokenSilent(request);
    return response.accessToken;
  } catch {
    try {
      const response = await msalInstance.acquireTokenPopup({ scopes: API_SCOPES });
      return response.accessToken;
    } catch (popupError) {
      console.error("Failed to acquire token:", popupError);
      return null;
    }
  }
}

// --- Axios Instance ---
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor for auth
apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    const token = await getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      console.warn("Unauthorized - token may be expired");
      // Optionally trigger re-authentication
    }
    return Promise.reject(error);
  }
);

// --- Analytics API ---
export const analyticsApi = {
  getKPIs: async (): Promise<KPIData> => {
    const response = await apiClient.get<KPIData>("/api/v1/analytics/kpis");
    return response.data;
  },

  getDemandForecast: async (): Promise<DemandForecast[]> => {
    const response = await apiClient.get<DemandForecast[]>("/api/v1/analytics/demand-forecast");
    return response.data;
  },

  getPipelineStatus: async (): Promise<PipelineStatus[]> => {
    const response = await apiClient.get<PipelineStatus[]>("/api/v1/analytics/pipeline-status");
    return response.data;
  },
};

// --- Chat API ---
export const chatApi = {
  sendMessage: async (
    agentId: string,
    messages: Array<{ role: string; content: string }>
  ): Promise<ChatMessage> => {
    const response = await apiClient.post<{
      id: string;
      content: string;
      citations: Citation[];
    }>("/api/v1/chat", {
      agent_id: agentId,
      messages,
      stream: false,
    });

    return {
      id: response.data.id,
      role: "assistant",
      content: response.data.content,
      timestamp: new Date().toISOString(),
      agentId,
      citations: response.data.citations,
    };
  },

  sendMessageStream: async (
    agentId: string,
    messages: Array<{ role: string; content: string }>,
    onChunk: (chunk: string) => void,
    onComplete: (citations: Citation[]) => void,
    onError: (error: Error) => void
  ): Promise<void> => {
    try {
      const token = await getAccessToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          agent_id: agentId,
          messages,
          stream: true,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Response body is not readable");
      }

      const decoder = new TextDecoder();
      let citations: Citation[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value, { stream: true });
        const lines = text.split("\n");

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6).trim();

            if (data === "[DONE]") {
              onComplete(citations);
              return;
            }

            try {
              const parsed = JSON.parse(data);

              if (parsed.type === "content") {
                onChunk(parsed.content);
              } else if (parsed.type === "citations") {
                citations = parsed.citations;
              } else if (parsed.type === "error") {
                onError(new Error(parsed.message));
                return;
              }
            } catch {
              // Non-JSON line, treat as content chunk
              if (data) onChunk(data);
            }
          }
        }
      }

      onComplete(citations);
    } catch (error) {
      onError(error instanceof Error ? error : new Error("Stream failed"));
    }
  },
};

// --- Tickets API (Plane Integration) ---
export const ticketsApi = {
  listTickets: async (): Promise<Ticket[]> => {
    const response = await apiClient.get<Ticket[]>("/api/v1/tickets");
    return response.data;
  },

  getTicket: async (ticketId: string): Promise<Ticket> => {
    const response = await apiClient.get<Ticket>(`/api/v1/tickets/${ticketId}`);
    return response.data;
  },

  createTicket: async (payload: CreateTicketPayload): Promise<Ticket> => {
    const response = await apiClient.post<Ticket>("/api/v1/tickets", payload);
    return response.data;
  },

  updateTicket: async (
    ticketId: string,
    payload: Partial<CreateTicketPayload & { status: string }>
  ): Promise<Ticket> => {
    const response = await apiClient.patch<Ticket>(`/api/v1/tickets/${ticketId}`, payload);
    return response.data;
  },
};

export default apiClient;
