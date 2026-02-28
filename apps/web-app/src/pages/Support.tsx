import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  Search,
  Filter,
  ExternalLink,
  Clock,
  AlertCircle,
  CheckCircle2,
  Circle,
  Loader2,
  ChevronDown,
  X,
} from "lucide-react";
import { ticketsApi, type Ticket, type CreateTicketPayload } from "../services/api";

// --- Status & Priority Configs ---
const STATUS_CONFIG: Record<string, { label: string; icon: React.ReactNode; className: string }> = {
  backlog: { label: "Backlog", icon: <Circle className="w-3.5 h-3.5" />, className: "text-gray-500 bg-gray-50" },
  todo: { label: "To Do", icon: <Circle className="w-3.5 h-3.5" />, className: "text-blue-600 bg-blue-50" },
  in_progress: { label: "In Progress", icon: <Clock className="w-3.5 h-3.5" />, className: "text-yellow-600 bg-yellow-50" },
  done: { label: "Done", icon: <CheckCircle2 className="w-3.5 h-3.5" />, className: "text-green-600 bg-green-50" },
  cancelled: { label: "Cancelled", icon: <X className="w-3.5 h-3.5" />, className: "text-red-600 bg-red-50" },
};

const PRIORITY_CONFIG: Record<string, { label: string; className: string }> = {
  urgent: { label: "Urgent", className: "text-red-700 bg-red-100 border-red-200" },
  high: { label: "High", className: "text-orange-700 bg-orange-100 border-orange-200" },
  medium: { label: "Medium", className: "text-yellow-700 bg-yellow-100 border-yellow-200" },
  low: { label: "Low", className: "text-gray-600 bg-gray-100 border-gray-200" },
  none: { label: "None", className: "text-gray-400 bg-gray-50 border-gray-200" },
};

const LABELS = [
  "bug",
  "feature-request",
  "data-pipeline",
  "ai-agent",
  "infrastructure",
  "documentation",
  "performance",
  "security",
];

// --- Demo Tickets ---
const DEMO_TICKETS: Ticket[] = [
  {
    id: "TICKET-001",
    title: "Customer 360 ETL pipeline failing on PostgreSQL connection timeout",
    description:
      "The Customer 360 ETL pipeline has been intermittently failing due to PostgreSQL connection timeouts. The issue started after the latest database maintenance window.",
    status: "in_progress",
    priority: "high",
    assignee: "data-team@company.com",
    labels: ["bug", "data-pipeline"],
    created_at: "2026-02-27T14:30:00Z",
    updated_at: "2026-02-28T09:15:00Z",
  },
  {
    id: "TICKET-002",
    title: "Add streaming response support to AI Chat in production",
    description:
      "Enable SSE streaming for AI chat responses in the production environment. Currently only enabled in Dev and QA.",
    status: "todo",
    priority: "medium",
    assignee: "ml-engineer@company.com",
    labels: ["feature-request", "ai-agent"],
    created_at: "2026-02-26T10:00:00Z",
    updated_at: "2026-02-26T10:00:00Z",
  },
  {
    id: "TICKET-003",
    title: "Manufacturing QA Agent latency exceeds SLA threshold",
    description:
      "The Manufacturing QA Agent has average latency of 1200ms, exceeding the 1000ms SLA. Need to investigate model performance and optimize prompts.",
    status: "in_progress",
    priority: "urgent",
    assignee: "ml-engineer@company.com",
    labels: ["performance", "ai-agent"],
    created_at: "2026-02-28T08:00:00Z",
    updated_at: "2026-02-28T11:30:00Z",
  },
  {
    id: "TICKET-004",
    title: "Set up auto-scaling for App Service production instances",
    description:
      "Configure auto-scaling rules for the production App Service plan based on CPU and memory metrics.",
    status: "backlog",
    priority: "medium",
    assignee: "platform@company.com",
    labels: ["infrastructure"],
    created_at: "2026-02-25T16:00:00Z",
    updated_at: "2026-02-25T16:00:00Z",
  },
  {
    id: "TICKET-005",
    title: "Implement pgvector index optimization for semantic search",
    description:
      "The current IVFFlat index on the embeddings table needs to be replaced with HNSW for better recall at scale.",
    status: "done",
    priority: "high",
    assignee: "data-team@company.com",
    labels: ["performance", "data-pipeline"],
    created_at: "2026-02-20T09:00:00Z",
    updated_at: "2026-02-27T17:00:00Z",
  },
];

// --- Create Ticket Modal ---
interface CreateTicketModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (ticket: CreateTicketPayload) => void;
  isSubmitting: boolean;
}

function CreateTicketModal({ isOpen, onClose, onSubmit, isSubmitting }: CreateTicketModalProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("medium");
  const [selectedLabels, setSelectedLabels] = useState<string[]>([]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    onSubmit({
      title: title.trim(),
      description: description.trim(),
      priority,
      labels: selectedLabels,
    });
    // Reset form
    setTitle("");
    setDescription("");
    setPriority("medium");
    setSelectedLabels([]);
  };

  const toggleLabel = (label: string) => {
    setSelectedLabels((prev) =>
      prev.includes(label) ? prev.filter((l) => l !== label) : [...prev, label]
    );
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Create Support Ticket</h2>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded-lg">
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Brief description of the issue"
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Detailed description including steps to reproduce, expected behavior, etc."
              rows={5}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Priority</label>
            <div className="flex gap-2">
              {Object.entries(PRIORITY_CONFIG).map(([key, config]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setPriority(key)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                    priority === key
                      ? config.className + " ring-2 ring-offset-1 ring-blue-400"
                      : "text-gray-500 bg-white border-gray-200 hover:bg-gray-50"
                  }`}
                >
                  {config.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Labels</label>
            <div className="flex flex-wrap gap-2">
              {LABELS.map((label) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => toggleLabel(label)}
                  className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                    selectedLabels.includes(label)
                      ? "bg-blue-100 text-blue-700 border-blue-300"
                      : "bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!title.trim() || isSubmitting}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Create Ticket
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// --- Support Page ---
export default function Support() {
  const queryClient = useQueryClient();
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [priorityFilter, setPriorityFilter] = useState<string>("all");
  const [showFilters, setShowFilters] = useState(false);

  // Fetch tickets from API (with demo fallback)
  const { data: tickets = DEMO_TICKETS, isLoading } = useQuery<Ticket[]>({
    queryKey: ["tickets"],
    queryFn: ticketsApi.listTickets,
    placeholderData: DEMO_TICKETS,
  });

  // Create ticket mutation
  const createTicketMutation = useMutation({
    mutationFn: ticketsApi.createTicket,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      setIsCreateModalOpen(false);
    },
    onError: () => {
      // Add ticket locally as fallback
      const newTicket: Ticket = {
        id: `TICKET-${String(tickets.length + 1).padStart(3, "0")}`,
        title: "New Ticket (created locally)",
        description: "",
        status: "backlog",
        priority: "medium",
        labels: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      queryClient.setQueryData<Ticket[]>(["tickets"], (old) => [newTicket, ...(old ?? [])]);
      setIsCreateModalOpen(false);
    },
  });

  // Filter tickets
  const filteredTickets = tickets.filter((ticket) => {
    const matchesSearch =
      !searchQuery ||
      ticket.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ticket.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ticket.id.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === "all" || ticket.status === statusFilter;
    const matchesPriority = priorityFilter === "all" || ticket.priority === priorityFilter;
    return matchesSearch && matchesStatus && matchesPriority;
  });

  // Ticket stats
  const stats = {
    total: tickets.length,
    open: tickets.filter((t) => ["backlog", "todo", "in_progress"].includes(t.status)).length,
    inProgress: tickets.filter((t) => t.status === "in_progress").length,
    done: tickets.filter((t) => t.status === "done").length,
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Support Tickets</h1>
          <p className="text-sm text-gray-500 mt-1">
            Create and track issues via Plane project management
          </p>
        </div>
        <button
          onClick={() => setIsCreateModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Ticket
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
          <div className="text-2xl font-bold text-gray-900">{stats.total}</div>
          <div className="text-xs text-gray-500 mt-1">Total Tickets</div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
          <div className="text-2xl font-bold text-blue-600">{stats.open}</div>
          <div className="text-xs text-gray-500 mt-1">Open</div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
          <div className="text-2xl font-bold text-yellow-600">{stats.inProgress}</div>
          <div className="text-xs text-gray-500 mt-1">In Progress</div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
          <div className="text-2xl font-bold text-green-600">{stats.done}</div>
          <div className="text-xs text-gray-500 mt-1">Completed</div>
        </div>
      </div>

      {/* Search & Filters */}
      <div className="bg-white rounded-xl border border-gray-200 mb-6">
        <div className="flex items-center gap-3 p-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search tickets by title, description, or ID..."
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 px-4 py-2 text-sm border rounded-lg transition-colors ${
              showFilters ? "bg-blue-50 border-blue-300 text-blue-700" : "border-gray-300 text-gray-700 hover:bg-gray-50"
            }`}
          >
            <Filter className="w-4 h-4" />
            Filters
            <ChevronDown className={`w-4 h-4 transition-transform ${showFilters ? "rotate-180" : ""}`} />
          </button>
        </div>

        {showFilters && (
          <div className="flex items-center gap-4 px-4 pb-4 border-t border-gray-100 pt-3">
            <div>
              <label className="text-xs font-medium text-gray-500 mb-1 block">Status</label>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="text-sm border border-gray-300 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="all">All Statuses</option>
                {Object.entries(STATUS_CONFIG).map(([key, config]) => (
                  <option key={key} value={key}>{config.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500 mb-1 block">Priority</label>
              <select
                value={priorityFilter}
                onChange={(e) => setPriorityFilter(e.target.value)}
                className="text-sm border border-gray-300 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="all">All Priorities</option>
                {Object.entries(PRIORITY_CONFIG).map(([key, config]) => (
                  <option key={key} value={key}>{config.label}</option>
                ))}
              </select>
            </div>
          </div>
        )}
      </div>

      {/* Ticket List */}
      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
        </div>
      ) : filteredTickets.length === 0 ? (
        <div className="text-center py-16">
          <AlertCircle className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-700">No tickets found</h3>
          <p className="text-sm text-gray-500 mt-2">
            {searchQuery ? "Try adjusting your search or filters" : "Create your first support ticket to get started"}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredTickets.map((ticket) => {
            const status = STATUS_CONFIG[ticket.status] ?? STATUS_CONFIG.backlog;
            const priority = PRIORITY_CONFIG[ticket.priority] ?? PRIORITY_CONFIG.none;

            return (
              <div
                key={ticket.id}
                className="bg-white rounded-xl border border-gray-200 p-5 hover:border-gray-300 hover:shadow-sm transition-all"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-xs font-mono text-gray-400">{ticket.id}</span>
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full ${status.className}`}>
                        {status.icon}
                        {status.label}
                      </span>
                      <span className={`px-2 py-0.5 text-xs font-medium rounded-full border ${priority.className}`}>
                        {priority.label}
                      </span>
                    </div>
                    <h3 className="text-sm font-medium text-gray-900">{ticket.title}</h3>
                    {ticket.description && (
                      <p className="text-xs text-gray-500 mt-1 line-clamp-2">{ticket.description}</p>
                    )}
                    <div className="flex items-center gap-4 mt-3">
                      {ticket.labels?.map((label) => (
                        <span key={label} className="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded-full">
                          {label}
                        </span>
                      ))}
                      {ticket.assignee && (
                        <span className="text-xs text-gray-400">Assigned to: {ticket.assignee}</span>
                      )}
                      <span className="text-xs text-gray-400">
                        Created: {new Date(ticket.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                  <a
                    href={`#ticket-${ticket.id}`}
                    className="flex items-center gap-1 px-3 py-1.5 text-xs text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    View
                  </a>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Ticket Modal */}
      <CreateTicketModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onSubmit={(payload) => createTicketMutation.mutate(payload)}
        isSubmitting={createTicketMutation.isPending}
      />
    </div>
  );
}
