import { useEffect, useMemo, useState } from "react";

import { AuthPanel } from "./components/AuthPanel";
import { QueryComposer } from "./components/QueryComposer";
import { ThreadSidebar } from "./components/ThreadSidebar";
import { ThreadView } from "./components/ThreadView";
import { useAuth } from "./hooks/useAuth";
import { useThreads } from "./hooks/useThreads";
import { listCustomers, listMaterials, listOrders } from "./services/api";
import type {
  AgentHint,
  CatalogCustomer,
  CatalogMaterial,
  ChatModelOption,
  MatFormPayload,
  OrderItem,
} from "./types";

const AGENT_BUTTONS: Array<{ id: AgentHint; label: string }> = [
  { id: "agent_material_queries", label: "Agent Material Queries" },
  { id: "agent_polymer_specialist", label: "Agent Polymer Specialist" },
  { id: "agent_customer_service", label: "Agent Customer Service" },
  { id: "agent_complains_management", label: "Agent Complains Management" },
];

type ServiceAction = "quote" | "confirm" | "eta";

export default function App() {
  const { currentUser, register, login, logout } = useAuth();
  const {
    threads,
    activeThread,
    activeThreadId,
    storageWarning,
    isSending,
    createThread,
    selectThread,
    renameThread,
    deleteThread,
    sendQuery,
  } = useThreads(currentUser);

  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [selectedModel, setSelectedModel] = useState<ChatModelOption>("gpt-4.1-nano");
  const [answerViewMode, setAnswerViewMode] = useState<"structured" | "raw">("structured");
  const [selectedAgent, setSelectedAgent] = useState<AgentHint>("agent_material_queries");

  const [customers, setCustomers] = useState<CatalogCustomer[]>([]);
  const [materials, setMaterials] = useState<CatalogMaterial[]>([]);
  const [catalogWarning, setCatalogWarning] = useState<string | null>(null);

  const [serviceAction, setServiceAction] = useState<ServiceAction>("quote");
  const [serviceOrders, setServiceOrders] = useState<OrderItem[]>([]);
  const [complaintOrders, setComplaintOrders] = useState<OrderItem[]>([]);

  const [serviceForm, setServiceForm] = useState<MatFormPayload>({
    customer_name: "",
    contact_person: "",
    phone_number: "",
    material_name: "",
    quantity_tons: undefined,
    price_cny_per_kg: undefined,
    requested_delivery_time: "",
    order_no: "",
  });

  const [complaintForm, setComplaintForm] = useState<MatFormPayload>({
    customer_name: "",
    order_no: "",
    ticket_no: "",
    complaint_title: "",
    complaint_description: "",
    severity: "medium",
  });

  useEffect(() => {
    if (!currentUser) {
      return;
    }
    let cancelled = false;
    async function loadCatalog() {
      try {
        const [loadedCustomers, loadedMaterials] = await Promise.all([listCustomers(), listMaterials()]);
        if (cancelled) {
          return;
        }
        setCustomers(loadedCustomers);
        setMaterials(loadedMaterials);
        setCatalogWarning(null);
      } catch (error) {
        if (cancelled) {
          return;
        }
        const message = error instanceof Error ? error.message : "Unknown error";
        setCatalogWarning(`Catalog sync warning: ${message}`);
      }
    }
    void loadCatalog();
    return () => {
      cancelled = true;
    };
  }, [currentUser]);

  useEffect(() => {
    const customer = (serviceForm.customer_name ?? "").trim();
    if (!customer) {
      setServiceOrders([]);
      return;
    }
    let cancelled = false;
    async function loadOrders() {
      try {
        const orders = await listOrders(customer, 50);
        if (!cancelled) {
          setServiceOrders(orders);
        }
      } catch {
        if (!cancelled) {
          setServiceOrders([]);
        }
      }
    }
    void loadOrders();
    return () => {
      cancelled = true;
    };
  }, [serviceForm.customer_name]);

  useEffect(() => {
    const customer = (complaintForm.customer_name ?? "").trim();
    if (!customer) {
      setComplaintOrders([]);
      return;
    }
    let cancelled = false;
    async function loadOrders() {
      try {
        const orders = await listOrders(customer, 50);
        if (!cancelled) {
          setComplaintOrders(orders);
        }
      } catch {
        if (!cancelled) {
          setComplaintOrders([]);
        }
      }
    }
    void loadOrders();
    return () => {
      cancelled = true;
    };
  }, [complaintForm.customer_name]);

  const activeAgentLabel = useMemo(
    () => AGENT_BUTTONS.find((item) => item.id === selectedAgent)?.label ?? "Agent",
    [selectedAgent],
  );

  if (!currentUser) {
    return <AuthPanel onRegister={register} onLogin={login} />;
  }

  function selectedFormPayload(): MatFormPayload | undefined {
    if (selectedAgent === "agent_customer_service") {
      return serviceForm;
    }
    if (selectedAgent === "agent_complains_management") {
      return complaintForm;
    }
    return undefined;
  }

  function canSendWithoutTypedPrompt(): boolean {
    return selectedAgent === "agent_customer_service" || selectedAgent === "agent_complains_management";
  }

  function defaultPromptForCurrentAgent(): string {
    if (selectedAgent === "agent_customer_service") {
      if (serviceAction === "eta") {
        return "No prompt required: ETA request will be generated from selected customer/order fields.";
      }
      if (serviceAction === "confirm") {
        return "No prompt required: confirmation request will be generated from form fields.";
      }
      return "No prompt required: quote request will be generated from form fields.";
    }
    if (selectedAgent === "agent_complains_management") {
      return "No prompt required: complaint create/status request will be generated from form fields.";
    }
    return "Your Query - Your Project Description - We provide your solution!";
  }

  function buildEffectivePrompt(rawPrompt: string): string {
    const typed = rawPrompt.trim();
    if (typed) {
      return typed;
    }

    if (selectedAgent === "agent_customer_service") {
      const customer = (serviceForm.customer_name ?? "").trim() || "(missing customer)";
      const material = (serviceForm.material_name ?? "").trim() || "(missing material)";
      const qty = serviceForm.quantity_tons ?? "(missing quantity)";
      const orderNo = (serviceForm.order_no ?? "").trim() || "(missing order no)";
      const price = serviceForm.price_cny_per_kg ?? "auto";

      if (serviceAction === "eta") {
        return `Please check delivery ETA for order ${orderNo} for customer ${customer}.`;
      }
      if (serviceAction === "confirm") {
        return `Please confirm order for customer ${customer}, material ${material}, quantity ${qty} tons, price ${price} CNY/kg.`;
      }
      return `Please provide quote for customer ${customer}, material ${material}, quantity ${qty} tons, target price ${price} CNY/kg.`;
    }

    if (selectedAgent === "agent_complains_management") {
      const ticket = (complaintForm.ticket_no ?? "").trim();
      const title = (complaintForm.complaint_title ?? "").trim();
      const description = (complaintForm.complaint_description ?? "").trim();
      const customer = (complaintForm.customer_name ?? "").trim() || "(missing customer)";
      const orderNo = (complaintForm.order_no ?? "").trim() || "unspecified";
      const severity = (complaintForm.severity ?? "medium").trim();

      if (ticket && !title && !description) {
        return `Please check complaint status for ticket ${ticket}.`;
      }
      return `Please open complaint for customer ${customer}, order ${orderNo}, severity ${severity}, title '${title || "(missing title)"}', description '${description || "(missing description)"}'.`;
    }

    return typed;
  }

  function onServiceOrderSelect(orderNo: string): void {
    const order = serviceOrders.find((item) => item.order_no === orderNo);
    setServiceForm((prev) => {
      if (!order) {
        return { ...prev, order_no: orderNo };
      }
      return {
        ...prev,
        order_no: order.order_no,
        material_name: order.material_name,
        quantity_tons: order.quantity_tons,
        price_cny_per_kg: order.final_price_cny_per_kg,
      };
    });
  }

  return (
    <div className="app-shell">
      <ThreadSidebar
        username={currentUser}
        threads={threads}
        activeThreadId={activeThreadId}
        mobileOpen={mobileSidebarOpen}
        onToggleMobile={() => setMobileSidebarOpen((open) => !open)}
        onCreateThread={() => {
          createThread();
          setMobileSidebarOpen(false);
        }}
        onSelectThread={(threadId) => {
          selectThread(threadId);
          setMobileSidebarOpen(false);
        }}
        onRenameThread={renameThread}
        onDeleteThread={deleteThread}
        onLogout={logout}
      />

      <main className="chat-main">
        <header className="chat-header">
          <button
            type="button"
            className="mobile-only"
            onClick={() => setMobileSidebarOpen((open) => !open)}
          >
            Threads
          </button>
          <div>
            <h1>{activeThread?.title ?? "myMAT Multi-Agent"}</h1>
            <p>Agentic Materials Assistant - RAG + Business Operations</p>
          </div>
          <div className="view-toggle" role="group" aria-label="Answer view mode">
            <button
              type="button"
              className={answerViewMode === "structured" ? "active" : ""}
              onClick={() => setAnswerViewMode("structured")}
            >
              Structured
            </button>
            <button
              type="button"
              className={answerViewMode === "raw" ? "active" : ""}
              onClick={() => setAnswerViewMode("raw")}
            >
              Raw
            </button>
          </div>
        </header>

        <section className="agent-toolbar">
          <div className="agent-buttons">
            {AGENT_BUTTONS.map((agent) => (
              <button
                key={agent.id}
                type="button"
                className={selectedAgent === agent.id ? "agent-btn active" : "agent-btn"}
                onClick={() => setSelectedAgent(agent.id)}
              >
                {agent.label}
              </button>
            ))}
          </div>
          <div className="agent-active">Active: {activeAgentLabel}</div>
        </section>

        {selectedAgent === "agent_customer_service" ? (
          <section className="agent-panel">
            <h3>Customer Service Form</h3>
            <div className="agent-grid">
              <label>
                Action
                <select
                  value={serviceAction}
                  onChange={(event) => setServiceAction(event.target.value as ServiceAction)}
                >
                  <option value="quote">Quote</option>
                  <option value="confirm">Confirm Order</option>
                  <option value="eta">Check ETA</option>
                </select>
              </label>
              <label>
                Customer
                <select
                  value={serviceForm.customer_name ?? ""}
                  onChange={(event) =>
                    setServiceForm((prev) => ({
                      ...prev,
                      customer_name: event.target.value,
                      order_no: "",
                    }))
                  }
                >
                  <option value="">Select customer</option>
                  {customers.map((item) => (
                    <option key={item.customer_name} value={item.customer_name}>
                      {item.customer_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Existing Order (auto-fill)
                <select
                  value={serviceForm.order_no ?? ""}
                  onChange={(event) => onServiceOrderSelect(event.target.value)}
                >
                  <option value="">Select past order (optional)</option>
                  {serviceOrders.map((order) => (
                    <option key={order.order_no} value={order.order_no}>
                      {order.order_no} - {order.material_name} - {order.quantity_tons}t - {order.final_price_cny_per_kg} CNY/kg
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Material
                <select
                  value={serviceForm.material_name ?? ""}
                  onChange={(event) =>
                    setServiceForm((prev) => ({
                      ...prev,
                      material_name: event.target.value,
                    }))
                  }
                >
                  <option value="">Select material</option>
                  {materials.map((item) => (
                    <option key={item.material_name} value={item.material_name}>
                      {item.material_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Contact Person
                <input
                  value={serviceForm.contact_person ?? ""}
                  onChange={(event) =>
                    setServiceForm((prev) => ({ ...prev, contact_person: event.target.value }))
                  }
                />
              </label>
              <label>
                Phone Number
                <input
                  value={serviceForm.phone_number ?? ""}
                  onChange={(event) =>
                    setServiceForm((prev) => ({ ...prev, phone_number: event.target.value }))
                  }
                />
              </label>
              <label>
                Quantity (tons)
                <input
                  type="number"
                  step="0.01"
                  value={serviceForm.quantity_tons ?? ""}
                  onChange={(event) =>
                    setServiceForm((prev) => ({
                      ...prev,
                      quantity_tons: event.target.value ? Number(event.target.value) : undefined,
                    }))
                  }
                />
              </label>
              <label>
                Price (CNY/kg)
                <input
                  type="number"
                  step="0.01"
                  value={serviceForm.price_cny_per_kg ?? ""}
                  onChange={(event) =>
                    setServiceForm((prev) => ({
                      ...prev,
                      price_cny_per_kg: event.target.value ? Number(event.target.value) : undefined,
                    }))
                  }
                />
              </label>
              <label>
                Requested Delivery Date
                <input
                  type="date"
                  value={serviceForm.requested_delivery_time ?? ""}
                  onChange={(event) =>
                    setServiceForm((prev) => ({
                      ...prev,
                      requested_delivery_time: event.target.value,
                    }))
                  }
                />
              </label>
            </div>
          </section>
        ) : null}

        {selectedAgent === "agent_complains_management" ? (
          <section className="agent-panel">
            <h3>Complaints Form</h3>
            <div className="agent-grid">
              <label>
                Customer
                <select
                  value={complaintForm.customer_name ?? ""}
                  onChange={(event) =>
                    setComplaintForm((prev) => ({
                      ...prev,
                      customer_name: event.target.value,
                      order_no: "",
                    }))
                  }
                >
                  <option value="">Select customer</option>
                  {customers.map((item) => (
                    <option key={item.customer_name} value={item.customer_name}>
                      {item.customer_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Existing Order (optional)
                <select
                  value={complaintForm.order_no ?? ""}
                  onChange={(event) =>
                    setComplaintForm((prev) => ({ ...prev, order_no: event.target.value }))
                  }
                >
                  <option value="">Select past order (optional)</option>
                  {complaintOrders.map((order) => (
                    <option key={order.order_no} value={order.order_no}>
                      {order.order_no} - {order.material_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Ticket Number (status check)
                <input
                  value={complaintForm.ticket_no ?? ""}
                  onChange={(event) =>
                    setComplaintForm((prev) => ({ ...prev, ticket_no: event.target.value }))
                  }
                />
              </label>
              <label>
                Severity
                <select
                  value={complaintForm.severity ?? "medium"}
                  onChange={(event) =>
                    setComplaintForm((prev) => ({ ...prev, severity: event.target.value }))
                  }
                >
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                  <option value="critical">critical</option>
                </select>
              </label>
              <label className="wide">
                Complaint Title
                <input
                  value={complaintForm.complaint_title ?? ""}
                  onChange={(event) =>
                    setComplaintForm((prev) => ({ ...prev, complaint_title: event.target.value }))
                  }
                />
              </label>
              <label className="wide">
                Complaint Description
                <textarea
                  value={complaintForm.complaint_description ?? ""}
                  onChange={(event) =>
                    setComplaintForm((prev) => ({ ...prev, complaint_description: event.target.value }))
                  }
                />
              </label>
            </div>
          </section>
        ) : null}

        {storageWarning ? <div className="warning-banner">{storageWarning}</div> : null}
        {catalogWarning ? <div className="warning-banner">{catalogWarning}</div> : null}

        <ThreadView thread={activeThread} answerViewMode={answerViewMode} />

        <QueryComposer
          disabled={!currentUser}
          isSending={isSending}
          selectedModel={selectedModel}
          allowEmptySend={canSendWithoutTypedPrompt()}
          placeholder={defaultPromptForCurrentAgent()}
          onSelectModel={setSelectedModel}
          onSend={(query, model) => {
            const effectivePrompt = buildEffectivePrompt(query);
            if (!effectivePrompt.trim()) {
              return Promise.resolve();
            }
            return sendQuery(effectivePrompt, model, selectedAgent, selectedFormPayload());
          }}
        />
      </main>
    </div>
  );
}
