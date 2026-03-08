import type {
  AgentHint,
  CatalogCustomer,
  CatalogMaterial,
  ChatModelOption,
  ComplaintResponse,
  ConfirmOrderResponse,
  MatFormPayload,
  MatQueryResponse,
  OrderItem,
  QuoteResponse,
  Role,
  ThreadMessageApi,
  ThreadSummaryApi,
} from "../types";

interface HistoryMessage {
  role: Role;
  content: string;
}

interface RetrievalOptions {
  k?: number;
  search_type?: "similarity" | "mmr";
  fetch_k?: number;
  lambda_mult?: number;
  doc_type?: string;
  source_contains?: string;
}

interface MatQueryRequest {
  username?: string;
  thread_id?: string;
  message: string;
  selected_agent_hint?: AgentHint;
  chat_model?: ChatModelOption;
  form_payload?: MatFormPayload;
  history?: HistoryMessage[];
  retrieval?: RetrievalOptions;
}

interface CreateThreadRequest {
  username: string;
  thread_id?: string;
  title?: string;
}

interface CreateThreadResponse {
  thread: ThreadSummaryApi;
}

interface RenameThreadRequest {
  username: string;
  title: string;
}

interface RenameThreadResponse {
  thread: ThreadSummaryApi;
}

interface DeleteThreadResponse {
  deleted: boolean;
  thread_id: string;
}

interface ListThreadsResponse {
  threads: ThreadSummaryApi[];
}

interface GetThreadMessagesResponse {
  thread: ThreadSummaryApi;
  messages: ThreadMessageApi[];
}

interface CatalogCustomersResponse {
  customers: CatalogCustomer[];
}

interface CatalogMaterialsResponse {
  materials: CatalogMaterial[];
}

interface OrdersResponse {
  orders: OrderItem[];
}

interface QuoteRequest {
  customer_name: string;
  material_name: string;
  quantity_tons: number;
  price_cny_per_kg?: number;
  requested_delivery_time?: string;
}

interface ConfirmOrderRequest extends QuoteRequest {
  contact_person?: string;
  phone_number?: string;
}

interface ComplaintCreateRequest {
  customer_name: string;
  title: string;
  description: string;
  severity?: string;
  order_no?: string;
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

function apiUrl(path: string): string {
  if (!API_BASE_URL) {
    return path;
  }
  return `${API_BASE_URL}${path}`;
}

const DEFAULT_RETRIEVAL: Required<
  Pick<RetrievalOptions, "k" | "search_type" | "fetch_k" | "lambda_mult">
> = {
  k: 8,
  search_type: "mmr",
  fetch_k: 40,
  lambda_mult: 0.35,
};

async function parseError(response: Response, fallbackPrefix: string): Promise<never> {
  let detail = "Unknown server error";
  try {
    const json = (await response.json()) as { detail?: unknown; error?: string; message?: string };
    if (typeof json.detail === "string") {
      detail = json.detail;
    } else if (json.detail && typeof json.detail === "object") {
      detail = JSON.stringify(json.detail);
    } else if (json.error || json.message) {
      detail = `${json.error ?? "error"}: ${json.message ?? ""}`.trim();
    }
  } catch {
    detail = response.statusText || detail;
  }
  throw new Error(`${fallbackPrefix} (${response.status}): ${detail}`);
}

export async function queryMat(payload: MatQueryRequest): Promise<MatQueryResponse> {
  const requestPayload: MatQueryRequest = {
    ...payload,
    retrieval: {
      ...DEFAULT_RETRIEVAL,
      ...(payload.retrieval ?? {}),
    },
  };

  const response = await fetch(apiUrl("/api/mat/query"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestPayload),
  });

  if (!response.ok) {
    await parseError(response, "Query failed");
  }

  return (await response.json()) as MatQueryResponse;
}

export async function listThreads(username: string, limit = 50): Promise<ThreadSummaryApi[]> {
  const response = await fetch(
    apiUrl(`/api/threads?username=${encodeURIComponent(username)}&limit=${limit}`),
  );
  if (!response.ok) {
    await parseError(response, "List threads failed");
  }
  const payload = (await response.json()) as ListThreadsResponse;
  return payload.threads ?? [];
}

export async function createThread(payload: CreateThreadRequest): Promise<ThreadSummaryApi> {
  const response = await fetch(apiUrl("/api/threads"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await parseError(response, "Create thread failed");
  }
  const json = (await response.json()) as CreateThreadResponse;
  return json.thread;
}

export async function getThreadMessages(
  username: string,
  threadId: string,
  limit = 500,
): Promise<GetThreadMessagesResponse> {
  const response = await fetch(
    apiUrl(
      `/api/threads/${encodeURIComponent(threadId)}/messages?username=${encodeURIComponent(username)}&limit=${limit}`,
    ),
  );
  if (!response.ok) {
    await parseError(response, "Get thread messages failed");
  }
  return (await response.json()) as GetThreadMessagesResponse;
}

export async function renameThread(
  threadId: string,
  payload: RenameThreadRequest,
): Promise<ThreadSummaryApi> {
  const response = await fetch(apiUrl(`/api/threads/${encodeURIComponent(threadId)}`), {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await parseError(response, "Rename thread failed");
  }
  const payloadJson = (await response.json()) as RenameThreadResponse;
  return payloadJson.thread;
}

export async function deleteThread(username: string, threadId: string): Promise<DeleteThreadResponse> {
  const response = await fetch(
    apiUrl(`/api/threads/${encodeURIComponent(threadId)}?username=${encodeURIComponent(username)}`),
    {
      method: "DELETE",
    },
  );
  if (!response.ok) {
    await parseError(response, "Delete thread failed");
  }
  return (await response.json()) as DeleteThreadResponse;
}

export async function fetchHealth(): Promise<{
  status: string;
  collection: string;
  db_path: string;
  thread_memory_enabled?: boolean;
  thread_memory_ready?: boolean;
  ops_db_enabled?: boolean;
  ops_db_ready?: boolean;
}> {
  const response = await fetch(apiUrl("/api/health"));
  if (!response.ok) {
    throw new Error(`Health check failed (${response.status})`);
  }
  return (await response.json()) as {
    status: string;
    collection: string;
    db_path: string;
    thread_memory_enabled?: boolean;
    thread_memory_ready?: boolean;
    ops_db_enabled?: boolean;
    ops_db_ready?: boolean;
  };
}

export async function listCustomers(): Promise<CatalogCustomer[]> {
  const response = await fetch(apiUrl("/api/catalog/customers"));
  if (!response.ok) {
    await parseError(response, "List customers failed");
  }
  const json = (await response.json()) as CatalogCustomersResponse;
  return json.customers ?? [];
}

export async function listMaterials(): Promise<CatalogMaterial[]> {
  const response = await fetch(apiUrl("/api/catalog/materials"));
  if (!response.ok) {
    await parseError(response, "List materials failed");
  }
  const json = (await response.json()) as CatalogMaterialsResponse;
  return json.materials ?? [];
}

export async function quoteOrder(payload: QuoteRequest): Promise<QuoteResponse> {
  const response = await fetch(apiUrl("/api/orders/quote"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await parseError(response, "Quote failed");
  }
  return (await response.json()) as QuoteResponse;
}

export async function confirmOrder(payload: ConfirmOrderRequest): Promise<ConfirmOrderResponse> {
  const response = await fetch(apiUrl("/api/orders/confirm"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await parseError(response, "Confirm order failed");
  }
  return (await response.json()) as ConfirmOrderResponse;
}

export async function listOrders(customerName?: string, limit = 50): Promise<OrderItem[]> {
  const params = new URLSearchParams();
  if (customerName?.trim()) {
    params.set("customer_name", customerName.trim());
  }
  params.set("limit", String(limit));
  const response = await fetch(apiUrl(`/api/orders?${params.toString()}`));
  if (!response.ok) {
    await parseError(response, "List orders failed");
  }
  const payload = (await response.json()) as OrdersResponse;
  return payload.orders ?? [];
}

export async function createComplaint(payload: ComplaintCreateRequest): Promise<ComplaintResponse> {
  const response = await fetch(apiUrl("/api/complaints"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await parseError(response, "Create complaint failed");
  }
  return (await response.json()) as ComplaintResponse;
}

export async function getComplaint(ticketNo: string): Promise<ComplaintResponse> {
  const response = await fetch(apiUrl(`/api/complaints/${encodeURIComponent(ticketNo)}`));
  if (!response.ok) {
    await parseError(response, "Get complaint failed");
  }
  return (await response.json()) as ComplaintResponse;
}
