import { ApiError, requestJson } from "@/lib/api";

const BASE = "/api/entity-inbox";

// ── Types ────────────────────────────────────────────────────────────

export type ProposalStatus =
  | "pending"
  | "accepted_new"
  | "merged_existing"
  | "dismissed"
  | "rejected"
  | "blocked";

export type EntityType = "person" | "project";

export type CandidateMatch = {
  entity_id: number;
  canonical_name: string;
  score: number;
  signals: {
    exact_prefix: boolean;
    token_overlap: number;
    edit_distance_ratio: number;
  };
};

export type ProposalSummary = {
  id: number;
  entity_type: EntityType;
  status: ProposalStatus;
  surface_name: string;
  entry_date: string;
  life_event_id: number | null;
  created_at: string;
  resolved_at: string | null;
};

export type PersonMentionPayload = {
  name: string;
  relationship_hint: string | null;
  interaction_context: string | null;
  linked_event_hint: string | null;
  sentiment: string | null;
};

export type ProjectEventPayload = {
  project_name: string;
  event_type: string;
  description: string;
  linked_event_hint: string | null;
  suggested_project_status: string | null;
};

export type ProposalDetail = ProposalSummary & {
  payload: { mentions?: PersonMentionPayload[]; events?: ProjectEventPayload[] };
  candidate_matches: CandidateMatch[];
  resolution_entity_id: number | null;
  resolution_note: string | null;
};

export type ActionResult = {
  proposal: ProposalDetail;
  entity_id: number | null;
  mentions_created: number;
  events_created: number;
  status_transitions: number;
  cascaded_proposal_ids: number[];
  cascade_truncated: boolean;
  warnings: string[];
};

export type InboxSummary = {
  pending_person: number;
  pending_project: number;
  total_pending: number;
  oldest_pending_entry_date: string | null;
};

export type BlocklistEntry = {
  id: number;
  entity_type: EntityType;
  surface_name: string;
  reason: "manual_block" | "system_noise" | null;
  created_at: string;
};

export type ConfirmNewPersonBody = {
  canonical_name?: string | null;
  aliases?: string[];
  relationship_type?: string | null;
  notes?: string | null;
};

export type MergePersonBody = {
  target_entity_id: number;
  add_alias?: boolean;
  extra_aliases?: string[];
};

export type ConfirmNewProjectBody = {
  name?: string | null;
  aliases?: string[];
  category?: string | null;
  status?: "ACTIVE" | "PAUSED" | "COMPLETED" | "ABANDONED" | null;
  description?: string | null;
  target_date?: string | null;
};

export type MergeProjectBody = {
  target_entity_id: number;
  add_alias?: boolean;
  extra_aliases?: string[];
};

export type RejectProjectBody = {
  mode?: "dismiss" | "blocklist";
  note?: string | null;
};

export type DismissBody = { note?: string | null };

export type BlocklistBody = {
  reason?: "manual_block" | "system_noise";
  note?: string | null;
  cascade_pending?: boolean;
};

// ── Read endpoints ───────────────────────────────────────────────────

export type ListProposalsParams = {
  status?: ProposalStatus[];
  entity_type?: EntityType;
  entry_date_from?: string;
  entry_date_to?: string;
  search?: string;
  limit?: number;
  offset?: number;
};

function buildQuery(params: ListProposalsParams): string {
  const sp = new URLSearchParams();
  for (const s of params.status ?? ["pending"]) sp.append("status", s);
  if (params.entity_type) sp.set("entity_type", params.entity_type);
  if (params.entry_date_from) sp.set("entry_date_from", params.entry_date_from);
  if (params.entry_date_to) sp.set("entry_date_to", params.entry_date_to);
  if (params.search) sp.set("search", params.search);
  if (params.limit !== undefined) sp.set("limit", String(params.limit));
  if (params.offset !== undefined) sp.set("offset", String(params.offset));
  return sp.toString();
}

export async function listProposals(
  params: ListProposalsParams,
  signal?: AbortSignal
): Promise<{ total: number; items: ProposalSummary[] }> {
  const qs = buildQuery(params);
  return requestJson(`${BASE}/proposals${qs ? `?${qs}` : ""}`, { signal });
}

export async function getProposal(
  id: number,
  signal?: AbortSignal
): Promise<ProposalDetail> {
  return requestJson(`${BASE}/proposals/${id}`, { signal });
}

export async function getInboxSummary(
  signal?: AbortSignal
): Promise<InboxSummary> {
  return requestJson(`${BASE}/proposals/summary`, { signal });
}

export async function listBlocklist(
  entity_type?: EntityType,
  signal?: AbortSignal
): Promise<BlocklistEntry[]> {
  const qs = entity_type ? `?entity_type=${entity_type}` : "";
  return requestJson(`${BASE}/blocklist${qs}`, { signal });
}

export async function deleteBlocklistEntry(
  id: number,
  signal?: AbortSignal
): Promise<void> {
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const res = await fetch(`${apiBase}${BASE}/blocklist/${id}`, {
    method: "DELETE",
    signal,
  });
  if (!res.ok) {
    throw new ApiError(`Failed to delete blocklist entry (${res.status})`, res.status);
  }
}

// ── Action endpoints ─────────────────────────────────────────────────

type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

function postAction<T>(path: string, body: object): Promise<T> {
  return requestJson<T>(path, {
    method: "POST",
    body: body as unknown as JsonValue,
  });
}

export function confirmNewPerson(
  id: number,
  body: ConfirmNewPersonBody
): Promise<ActionResult> {
  return postAction<ActionResult>(
    `${BASE}/proposals/${id}/actions/confirm-new-person`,
    body
  );
}

export function mergePerson(
  id: number,
  body: MergePersonBody
): Promise<ActionResult> {
  return postAction<ActionResult>(`${BASE}/proposals/${id}/actions/merge-person`, body);
}

export function confirmNewProject(
  id: number,
  body: ConfirmNewProjectBody
): Promise<ActionResult> {
  return postAction<ActionResult>(
    `${BASE}/proposals/${id}/actions/confirm-new-project`,
    body
  );
}

export function mergeProject(
  id: number,
  body: MergeProjectBody
): Promise<ActionResult> {
  return postAction<ActionResult>(`${BASE}/proposals/${id}/actions/merge-project`, body);
}

export function rejectProject(
  id: number,
  body: RejectProjectBody
): Promise<ActionResult> {
  return postAction<ActionResult>(`${BASE}/proposals/${id}/actions/reject-project`, body);
}

export function dismissProposal(
  id: number,
  body: DismissBody
): Promise<ActionResult> {
  return postAction<ActionResult>(`${BASE}/proposals/${id}/actions/dismiss`, body);
}

export function blocklistProposal(
  id: number,
  body: BlocklistBody
): Promise<ActionResult> {
  return postAction<ActionResult>(`${BASE}/proposals/${id}/actions/blocklist`, body);
}

// ── Cached summary ───────────────────────────────────────────────────

let _summaryCache: { value: InboxSummary; fetchedAt: number } | null = null;
const SUMMARY_TTL_MS = 30_000;

export function invalidateInboxSummary(): void {
  _summaryCache = null;
}

export async function getCachedInboxSummary(
  signal?: AbortSignal
): Promise<InboxSummary> {
  const now = Date.now();
  if (_summaryCache && now - _summaryCache.fetchedAt < SUMMARY_TTL_MS) {
    return _summaryCache.value;
  }
  const value = await getInboxSummary(signal);
  _summaryCache = { value, fetchedAt: now };
  return value;
}
