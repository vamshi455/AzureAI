import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Bot, User, Loader2, RotateCcw, Copy, Check, ChevronDown } from "lucide-react";
import ChatMessage from "../components/ChatMessage";
import { chatApi, type ChatMessage as ChatMessageType, type Citation } from "../services/api";

// --- Agent Selector ---
const AGENTS = [
  { id: "sales-forecast-agent", name: "Sales Forecasting", description: "Analyze sales data and generate forecasts" },
  { id: "customer-support-agent", name: "Customer Support", description: "Help with orders, products, and warranties" },
  { id: "manufacturing-qa-agent", name: "Manufacturing QA", description: "Quality analysis and defect detection" },
  { id: "inventory-optimization-agent", name: "Inventory Optimization", description: "Stock levels and reorder recommendations" },
];

interface Conversation {
  id: string;
  messages: ChatMessageType[];
  agentId: string;
  title: string;
  createdAt: Date;
}

export default function AIChat() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState(AGENTS[0]);
  const [showAgentDropdown, setShowAgentDropdown] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const activeConversation = conversations.find((c) => c.id === activeConversationId);
  const messages = activeConversation?.messages ?? [];

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    const target = e.target;
    target.style.height = "auto";
    target.style.height = `${Math.min(target.scrollHeight, 200)}px`;
  };

  const createNewConversation = useCallback((): string => {
    const id = `conv-${Date.now()}`;
    const newConversation: Conversation = {
      id,
      messages: [],
      agentId: selectedAgent.id,
      title: "New Conversation",
      createdAt: new Date(),
    };
    setConversations((prev) => [newConversation, ...prev]);
    setActiveConversationId(id);
    return id;
  }, [selectedAgent]);

  const handleSendMessage = async () => {
    const trimmed = inputValue.trim();
    if (!trimmed || isStreaming) return;

    // Create conversation if needed
    let convId = activeConversationId;
    if (!convId) {
      convId = createNewConversation();
    }

    // Add user message
    const userMessage: ChatMessageType = {
      id: `msg-${Date.now()}`,
      role: "user",
      content: trimmed,
      timestamp: new Date().toISOString(),
    };

    setConversations((prev) =>
      prev.map((c) => {
        if (c.id === convId) {
          const updated = { ...c, messages: [...c.messages, userMessage] };
          // Update title from first user message
          if (c.messages.length === 0) {
            updated.title = trimmed.slice(0, 50) + (trimmed.length > 50 ? "..." : "");
          }
          return updated;
        }
        return c;
      })
    );

    setInputValue("");
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
    }

    // Create placeholder assistant message
    const assistantMessageId = `msg-${Date.now() + 1}`;
    const assistantMessage: ChatMessageType = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
      agentId: selectedAgent.id,
      citations: [],
      isStreaming: true,
    };

    setConversations((prev) =>
      prev.map((c) =>
        c.id === convId ? { ...c, messages: [...c.messages, assistantMessage] } : c
      )
    );

    setIsStreaming(true);

    try {
      // Attempt streaming from API
      const allMessages = [
        ...messages.map((m) => ({ role: m.role, content: m.content })),
        { role: "user" as const, content: trimmed },
      ];

      await chatApi.sendMessageStream(
        selectedAgent.id,
        allMessages,
        // onChunk callback
        (chunk: string) => {
          setConversations((prev) =>
            prev.map((c) =>
              c.id === convId
                ? {
                    ...c,
                    messages: c.messages.map((m) =>
                      m.id === assistantMessageId
                        ? { ...m, content: m.content + chunk }
                        : m
                    ),
                  }
                : c
            )
          );
        },
        // onComplete callback
        (citations: Citation[]) => {
          setConversations((prev) =>
            prev.map((c) =>
              c.id === convId
                ? {
                    ...c,
                    messages: c.messages.map((m) =>
                      m.id === assistantMessageId
                        ? { ...m, isStreaming: false, citations }
                        : m
                    ),
                  }
                : c
            )
          );
          setIsStreaming(false);
        },
        // onError callback
        () => {
          // Fallback: generate a demo response
          const demoResponse = generateDemoResponse(trimmed, selectedAgent.id);
          setConversations((prev) =>
            prev.map((c) =>
              c.id === convId
                ? {
                    ...c,
                    messages: c.messages.map((m) =>
                      m.id === assistantMessageId
                        ? {
                            ...m,
                            content: demoResponse.content,
                            citations: demoResponse.citations,
                            isStreaming: false,
                          }
                        : m
                    ),
                  }
                : c
            )
          );
          setIsStreaming(false);
        }
      );
    } catch {
      // Fallback demo response
      const demoResponse = generateDemoResponse(trimmed, selectedAgent.id);
      setConversations((prev) =>
        prev.map((c) =>
          c.id === convId
            ? {
                ...c,
                messages: c.messages.map((m) =>
                  m.id === assistantMessageId
                    ? {
                        ...m,
                        content: demoResponse.content,
                        citations: demoResponse.citations,
                        isStreaming: false,
                      }
                    : m
                ),
              }
            : c
        )
      );
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="flex h-[calc(100vh-8rem)]">
      {/* Conversation Sidebar */}
      <div className="w-72 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-4 border-b border-gray-200">
          <button
            onClick={() => {
              const id = createNewConversation();
              setActiveConversationId(id);
            }}
            className="w-full px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
          >
            New Conversation
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {conversations.map((conv) => (
            <button
              key={conv.id}
              onClick={() => setActiveConversationId(conv.id)}
              className={`w-full text-left px-4 py-3 border-b border-gray-100 hover:bg-gray-50 transition-colors ${
                conv.id === activeConversationId ? "bg-blue-50 border-l-2 border-l-blue-600" : ""
              }`}
            >
              <div className="text-sm font-medium text-gray-900 truncate">{conv.title}</div>
              <div className="text-xs text-gray-500 mt-1">
                {AGENTS.find((a) => a.id === conv.agentId)?.name} | {conv.messages.length} messages
              </div>
            </button>
          ))}
          {conversations.length === 0 && (
            <div className="p-6 text-center text-sm text-gray-400">
              No conversations yet. Start a new one!
            </div>
          )}
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Agent Selector */}
        <div className="bg-white border-b border-gray-200 px-6 py-3">
          <div className="relative">
            <button
              onClick={() => setShowAgentDropdown(!showAgentDropdown)}
              className="flex items-center gap-2 px-4 py-2 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
            >
              <Bot className="w-4 h-4 text-blue-600" />
              <span className="text-sm font-medium">{selectedAgent.name}</span>
              <ChevronDown className="w-4 h-4 text-gray-400" />
            </button>
            {showAgentDropdown && (
              <div className="absolute top-full left-0 mt-1 w-80 bg-white rounded-lg shadow-lg border border-gray-200 z-10">
                {AGENTS.map((agent) => (
                  <button
                    key={agent.id}
                    onClick={() => {
                      setSelectedAgent(agent);
                      setShowAgentDropdown(false);
                    }}
                    className={`w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors ${
                      agent.id === selectedAgent.id ? "bg-blue-50" : ""
                    }`}
                  >
                    <div className="text-sm font-medium text-gray-900">{agent.name}</div>
                    <div className="text-xs text-gray-500">{agent.description}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <Bot className="w-16 h-16 text-gray-300 mb-4" />
              <h3 className="text-lg font-medium text-gray-700">Start a conversation</h3>
              <p className="text-sm text-gray-500 mt-2 max-w-md">
                Ask {selectedAgent.name} a question about your data.
                Try: "What are the top selling products this quarter?"
              </p>
              <div className="grid grid-cols-2 gap-3 mt-6 max-w-lg">
                {getSuggestedPrompts(selectedAgent.id).map((prompt, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      setInputValue(prompt);
                      inputRef.current?.focus();
                    }}
                    className="text-left px-4 py-3 text-xs bg-white border border-gray-200 rounded-lg hover:border-blue-300 hover:bg-blue-50 transition-colors"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="bg-white border-t border-gray-200 px-6 py-4">
          <div className="flex items-end gap-3 max-w-4xl mx-auto">
            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                value={inputValue}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder={`Ask ${selectedAgent.name} a question...`}
                rows={1}
                disabled={isStreaming}
                className="w-full resize-none rounded-xl border border-gray-300 px-4 py-3 pr-12 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
              />
            </div>
            <button
              onClick={handleSendMessage}
              disabled={!inputValue.trim() || isStreaming}
              className="flex items-center justify-center w-10 h-10 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isStreaming ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Send className="w-5 h-5" />
              )}
            </button>
          </div>
          <div className="text-center mt-2">
            <span className="text-xs text-gray-400">
              AI responses may not always be accurate. Verify important information.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- Helper: Suggested prompts per agent ---
function getSuggestedPrompts(agentId: string): string[] {
  const prompts: Record<string, string[]> = {
    "sales-forecast-agent": [
      "What are the projected Q3 sales for the Northeast region?",
      "Show me the top 10 products by revenue this month",
      "How do current sales compare to last year?",
      "What seasonal trends should we prepare for?",
    ],
    "customer-support-agent": [
      "Help me look up order #12345",
      "What is the warranty policy for industrial pumps?",
      "How do I return a defective product?",
      "What are the shipping options for bulk orders?",
    ],
    "manufacturing-qa-agent": [
      "What is the current defect rate on Line B?",
      "Show me sensor anomalies from the past 24 hours",
      "Which equipment is due for maintenance?",
      "Analyze quality metrics for batch #7892",
    ],
    "inventory-optimization-agent": [
      "Which items are below reorder point?",
      "What is the recommended safety stock for SKU-2045?",
      "Show me slow-moving inventory items",
      "Calculate optimal reorder quantity for top sellers",
    ],
  };
  return prompts[agentId] ?? prompts["sales-forecast-agent"];
}

// --- Helper: Generate demo response ---
function generateDemoResponse(query: string, agentId: string): { content: string; citations: Citation[] } {
  const responses: Record<string, string> = {
    "sales-forecast-agent": `Based on my analysis of the historical sales data and current market indicators, here is my assessment:

## Key Findings

| Metric | Current | Last Period | Change |
|--------|---------|-------------|--------|
| Revenue | $2.4M | $2.1M | +14.3% |
| Orders | 3,421 | 3,102 | +10.3% |
| Avg Order Value | $701 | $677 | +3.5% |

### Trend Analysis

The data shows a **positive upward trajectory** driven primarily by:

1. **Seasonal demand increase** in industrial components
2. **New customer acquisition** in the Southeast market
3. **Price optimization** implemented in Q1

### Forecast

Based on the ARIMA model with seasonal decomposition:
- **Next 30 days**: $2.6M (+8.3% MoM)
- **Confidence interval**: $2.4M - $2.8M (85% CI)

\`\`\`python
# Forecast model parameters
model_params = {
    "order": (2, 1, 1),
    "seasonal_order": (1, 1, 1, 12),
    "trend": "ct"
}
\`\`\`

> **Note**: The forecast accounts for the upcoming seasonal dip typically observed in March.`,

    "customer-support-agent": `I'd be happy to help you with that! Let me look into this for you.

Based on your query, here is what I found:

### Order Information

The order has been processed and is currently in the following status:

- **Status**: In Transit
- **Estimated Delivery**: March 3, 2026
- **Carrier**: FedEx Ground
- **Tracking**: Available in your account dashboard

### Additional Resources

If you need further assistance, you can:
1. Track your shipment in real-time via the dashboard
2. Contact our logistics team at logistics@company.com
3. Submit a support ticket for priority handling

Is there anything else I can help you with?`,

    "manufacturing-qa-agent": `## Quality Analysis Report

### Current Production Metrics

| Line | OEE | Defect Rate | Throughput |
|------|-----|-------------|------------|
| Line A | 94.2% | 0.8% | 1,240 units/hr |
| Line B | 87.5% | 2.3% | 980 units/hr |
| Line C | 91.8% | 1.1% | 1,100 units/hr |
| Line D | 96.1% | 0.4% | 1,350 units/hr |

### Anomaly Detection

**Line B** shows elevated defect rates. Root cause analysis indicates:

1. **Sensor drift** detected on temperature probe T-204 (calibration due)
2. **Vibration anomaly** on motor M-12 (bearing wear pattern)
3. **Material variance** in batch RAW-2026-0892

### Recommended Actions

- **Immediate**: Recalibrate T-204 temperature probe
- **Scheduled**: Replace M-12 motor bearings (next maintenance window)
- **Investigation**: Quality hold on batch RAW-2026-0892 pending analysis`,

    "inventory-optimization-agent": `## Inventory Optimization Analysis

### Items Below Reorder Point

| SKU | Product | On Hand | Reorder Point | Lead Time |
|-----|---------|---------|---------------|-----------|
| SKU-2045 | Industrial Valve A | 45 | 120 | 14 days |
| SKU-3891 | Connector Kit B | 12 | 50 | 7 days |
| SKU-1203 | Sensor Module C | 8 | 25 | 21 days |

### Recommended Orders

Based on EOQ model with demand variability:

1. **SKU-2045**: Order 500 units (EOQ) - **Priority: HIGH**
2. **SKU-3891**: Order 200 units (EOQ) - **Priority: MEDIUM**
3. **SKU-1203**: Order 100 units (EOQ) - **Priority: HIGH** (long lead time)

### Cost Impact

- **Current stockout risk**: $45,200/month
- **Recommended carrying cost**: $12,800/month
- **Net savings**: $32,400/month`,
  };

  const content = responses[agentId] ?? responses["sales-forecast-agent"];
  const citations: Citation[] = [
    { title: "Sales Database - Q1 2026", source: "Fabric Lakehouse", url: "#" },
    { title: "Demand Forecast Model v2.4", source: "AI Foundry", url: "#" },
    { title: "Market Analysis Report", source: "Analytics Service", url: "#" },
  ];

  return { content, citations };
}
