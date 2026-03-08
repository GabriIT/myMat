export type Role = "user" | "assistant";
export type ChatModelOption = "gpt-4.1-nano" | "qwen3.5:9b" | "llama3.2:latest";

export type AgentHint =
  | "agent_material_queries"
  | "agent_polymer_specialist"
  | "agent_customer_service"
  | "agent_complains_management";

export interface AuthUser {
  username: string;
  passwordHash: string;
}

export interface SourceRef {
  source: string;
  source_name: string;
  doc_type: string;
  page_number?: number;
  sheet_name?: string;
}

export interface StructuredAnswer {
  prompt: string;
  bullets: string[];
  answer_text: string;
}

export interface ThreadMessage {
  id: string;
  role: Role;
  content: string;
  createdAt: string;
  structured?: StructuredAnswer;
  sources?: SourceRef[];
}

export interface ChatThread {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ThreadMessage[];
}

export interface QueryMeta {
  chat_model: string;
  embedding_model: string;
  k: number;
  search_type: "similarity" | "mmr";
  elapsed_ms: number;
  thread_memory_used?: boolean;
  thread_memory_ready?: boolean | null;
  thread_id?: string | null;
}

export interface QueryResponse {
  answer: string;
  structured?: StructuredAnswer;
  sources: SourceRef[];
  meta: QueryMeta;
}

export interface ThreadSummaryApi {
  thread_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview?: string | null;
}

export interface ThreadMessageApi {
  id: number;
  role: Role;
  content: string;
  created_at: string;
  structured?: StructuredAnswer;
  sources?: SourceRef[];
}

export interface MatFormPayload {
  customer_name?: string;
  contact_person?: string;
  phone_number?: string;
  material_name?: string;
  quantity_tons?: number;
  price_cny_per_kg?: number;
  requested_delivery_time?: string;
  order_no?: string;
  ticket_no?: string;
  complaint_title?: string;
  complaint_description?: string;
  severity?: string;
}

export interface MatQueryMeta {
  chat_model: string;
  routed_agent: AgentHint;
  elapsed_ms: number;
  used_web_fallback?: boolean;
  handoff_trace?: string[];
  fallback_used?: boolean;
  thread_id?: string | null;
}

export interface MatQueryResponse {
  routed_agent: AgentHint;
  answer_text: string;
  bullets: string[];
  sources: SourceRef[];
  follow_up_questions: string[];
  meta: MatQueryMeta;
}

export interface CatalogCustomer {
  customer_name: string;
  contact_person: string;
  phone_number: string;
}

export interface CatalogMaterial {
  material_name: string;
  category: string;
  base_price_cny_per_kg: number;
}

export interface QuoteResponse {
  customer_name: string;
  material_name: string;
  category: string;
  quantity_tons: number;
  unit_price_cny_per_kg: number;
  discount_pct: number;
  final_price_cny_per_kg: number;
  requested_delivery_time?: string;
  promised_delivery_from: string;
  promised_delivery_to: string;
}

export interface ConfirmOrderResponse extends QuoteResponse {
  order_id: number;
  order_no: string;
  status: string;
}

export interface ComplaintEvent {
  event_type: string;
  note: string;
  created_at: string;
}

export interface ComplaintResponse {
  ticket_no: string;
  customer_name: string;
  severity: string;
  status: string;
  title: string;
  description: string;
  created_at: string;
  updated_at?: string;
  events: ComplaintEvent[];
}
