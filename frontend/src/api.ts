// Thin client for the apnaSaathi API. Types mirror the backend's Pydantic models.
export type Lang = "en" | "hi";

export interface Chip { label: string; value: string }
export interface Slots {
  business_type?: string | null; segment?: string | null; city?: string | null;
  employees?: number | null; sites?: number | null; has_gstin?: boolean | null;
  needs?: string[]; needs_confirmed?: boolean; fibre_available?: boolean | null;
}
export interface AdvisorReply {
  session_id: string; language: Lang; text: string; expecting: string | null; chips: Chip[];
  show_form: boolean; missing: string[]; slots: Slots; understood_by: string; handoff: boolean;
  recommendation: unknown | null; summary: string | null;
}
export interface Saving { code: string; label: string; amount_inr: number }
export interface Priced {
  savings: Saving[]; earned_savings_fraction: number; list_monthly_inr: number; savings_monthly_inr: number;
  monthly_subtotal_inr: number; monthly_gst_inr: number; monthly_total_inr: number;
  one_time_subtotal_inr: number; one_time_gst_inr: number; one_time_total_inr: number; contract_months: number;
}
export interface Line {
  product_id: string; product_name: string; plain: string; icon: string; qty: number; unit: string;
  unit_price_inr: number; monthly_inr: number; list_monthly_inr: number; setup_inr: number; why: string;
  source: string; removable: boolean; adjustable_qty: boolean; max_qty: number;
}
export interface Addon { product_id: string; product_name: string; plain: string; icon: string; qty: number;
  unit: string; list_monthly_inr: number; why: string }
export interface Excluded { product_id: string; product_name: string; reason_code: string; message: string }
export interface Quote {
  id: string; status: string; language: Lang; business: string; city: string | null; city_tier: number;
  segment: string; lines: Line[]; addons: Addon[]; excluded: Excluded[]; notes: string[]; notices: string[];
  options: { commit_extra_12m: boolean; selfserve_autopay: boolean }; selfserve_saving_available: boolean;
  airfiber_available: boolean; using_airfiber: boolean; priced: Priced; order_id: string | null;
}
export interface OrderLine { product_id: string; product_name: string; plain: string; icon: string; qty: number;
  monthly_inr: number; install_days: number; expected_ready: string }
export interface Order {
  id: string; quote_id: string; state: string; business: string; city: string | null;
  contact_name_masked: string; contact_mobile_masked: string; lines: OrderLine[]; monthly_total_inr: number;
  one_time_total_inr: number; contract_months: number; expected_activation: string; next_step: string;
}
export type QuoteChange = Partial<{
  add: string; remove: string; set_qty: Record<string, number>; commit_extra_12m: boolean;
  selfserve_autopay: boolean; use_airfiber: boolean; language: Lang;
}>;

export interface KycCheck { code: string; doc_type: string | null; status: "pass" | "warn" | "fail";
  action: "block" | "fix" | "review" | null; message: string }
export interface KycCase {
  id: string; order_id: string | null; sample_id: string | null; language: Lang; consent_given: boolean;
  notice_version: string; purposes: string[]; gstin_masked: string | null; no_gstin: boolean; udyam_masked: string | null;
  gst_prefill: { legal_name: string; trade_name: string; constitution: string; address: string; status: string; source: string } | null;
  required_docs: string[]; uploaded: Record<string, { found_type: string | null; sharp: boolean; readable: boolean; deskewed: boolean }>;
  outcome: "VERIFIED" | "NEEDS_FIX" | "MANUAL_REVIEW" | "BLOCKED" | null; checks: KycCheck[]; retention_days: number;
}
export interface GstinResult { status: "ok" | "confirm" | "invalid" | "not_found" | "inactive"; message: string;
  suggestion: string | null; case: KycCase | null }
export interface Sample { id: string; business: string; city: string; documents: string[] }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  const res = await fetch(`/api${path}`, {
    method,
    headers: body && !isForm ? { "Content-Type": "application/json" } : undefined,
    body: body ? (isForm ? (body as FormData) : JSON.stringify(body)) : undefined,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail
        : Array.isArray(j.detail) ? j.detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, "")).join(" ")
        : msg;
    } catch { /* keep statusText */ }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  start: (language: Lang, channel = "web", partner_code?: string) =>
    call<AdvisorReply>("POST", "/advisor/sessions", { language, channel, partner_code }),
  message: (sid: string, text: string, language: Lang) =>
    call<AdvisorReply>("POST", `/advisor/sessions/${sid}/message`, { text, language }),
  form: (sid: string, slots: Slots, language: Lang) =>
    call<AdvisorReply>("POST", `/advisor/sessions/${sid}/form`, { slots, language }),
  createQuote: (session_id: string, language: Lang) => call<Quote>("POST", "/quotes", { session_id, language }),
  getQuote: (id: string, language: Lang) => call<Quote>("GET", `/quotes/${id}?language=${language}`),
  changeQuote: (id: string, ch: QuoteChange) => call<Quote>("PATCH", `/quotes/${id}`, ch),
  share: (id: string, language: Lang) => call<{ text: string }>("GET", `/quotes/${id}/share?language=${language}`),
  accept: (id: string, name: string, mobile: string, consent_contact: boolean) =>
    call<Order>("POST", `/quotes/${id}/accept`, { name, mobile, consent_contact }),
  kycCreate: (order_id: string, language: Lang) => call<KycCase>("POST", "/kyc/cases", { order_id, language }),
  kycConsent: (id: string, purposes: string[], notice_version: string) =>
    call<KycCase>("POST", `/kyc/cases/${id}/consent`, { purposes, notice_version }),
  kycGstin: (id: string, gstin: string | null, no_gstin = false) =>
    call<GstinResult>("POST", `/kyc/cases/${id}/gstin`, { gstin, no_gstin }),
  kycUdyam: (id: string, udyam_number: string | null) => call<KycCase>("POST", `/kyc/cases/${id}/udyam`, { udyam_number }),
  kycUpload: (id: string, doc_type: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return call<KycCase>("POST", `/kyc/cases/${id}/documents/${doc_type}`, fd);
  },
  kycEvaluate: (id: string) => call<KycCase>("POST", `/kyc/cases/${id}/evaluate`),
  kycWithdraw: (id: string) => call<KycCase>("DELETE", `/kyc/cases/${id}/documents`),
  kycSamples: () => call<Sample[]>("GET", "/kyc/samples"),
  kycUseSample: (id: string, kid: string) => call<KycCase>("POST", `/kyc/cases/${id}/use-sample/${kid}`),
};

const inrFmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
export const inr = (n: number) => `₹${inrFmt.format(n)}`;
