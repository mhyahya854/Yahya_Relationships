import type {
  AppState,
  BackupInfo,
  CompareResult,
  DuplicateCandidate,
  GeneralRelationshipFact,
  Group,
  HermesToolDef,
  Journal,
  MarriageFact,
  MutationPreviewResult,
  ParentChildFact,
  Person,
  RelationshipResult,
  SearchResult,
  SiblingGroupFact,
} from "./types";

let dynamicBaseUrl: string | null = null;
let dynamicUrlPromise: Promise<void> | null = null;

async function ensureDynamicUrl(): Promise<void> {
  if (dynamicBaseUrl) return;
  if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
    if (!dynamicUrlPromise) {
      dynamicUrlPromise = (async () => {
        try {
          const { invoke } = await import("@tauri-apps/api/core");
          const url = await invoke<string>("get_backend_url");
          if (url) {
            dynamicBaseUrl = url.replace(/\/$/, "");
          }
        } catch {
          dynamicBaseUrl = "http://127.0.0.1:8765";
        }
      })();
    }
    await dynamicUrlPromise;
  }
}

function apiBase(): string {
  if (dynamicBaseUrl) return dynamicBaseUrl;
  const configured = (import.meta.env.VITE_API_URL as string | undefined)?.trim();
  if (configured) return configured.replace(/\/$/, "");
  if (
    typeof window !== "undefined" &&
    "__TAURI_INTERNALS__" in window
  ) {
    return "http://127.0.0.1:8765";
  }
  return "";
}

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, unknown>;

  constructor(message: string, code: string, status: number, details: Record<string, unknown> = {}) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  await ensureDynamicUrl();
  const base = apiBase();
  const response = await fetch(`${base}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const body = (payload ?? {}) as {
      error?: { code?: string; message?: string; [key: string]: unknown };
    };
    throw new ApiError(
      body.error?.message ?? `Request failed (${response.status})`,
      body.error?.code ?? "HTTP_ERROR",
      response.status,
      (body.error ?? {}) as Record<string, unknown>,
    );
  }
  return payload as T;
}

export const api = {
  appInfo: () =>
    request<{
      ok: boolean;
      focus_person_id: string;
      focus_person_name: string | null;
      title: string;
      revision?: string;
      root: string;
    }>("/api/app/info"),

  state: {
    get: () => request<AppState>("/api/state"),
    set: (personId: string) =>
      request<AppState>("/api/state", {
        method: "PUT",
        body: JSON.stringify({ perspective_person_id: personId }),
      }),
    reset: () =>
      request<AppState>("/api/state/reset", { method: "POST" }),
  },

  mutations: {
    preview: (action: string, params: Record<string, unknown> = {}) =>
      request<{ ok: boolean } & MutationPreviewResult>("/api/mutations/preview", {
        method: "POST",
        body: JSON.stringify({ action, params }),
      }),
    undo: () =>
      request<{ ok: boolean; undone_description: string; can_undo_more: boolean }>("/api/mutations/undo", {
        method: "POST",
      }),
  },

  people: {
    list: (query?: string, groupId?: string) => {
      const params = new URLSearchParams();
      if (query) params.set("query", query);
      if (groupId) params.set("group_id", groupId);
      const suffix = params.toString() ? `?${params.toString()}` : "";
      return request<{ ok: boolean; people: Person[] }>(`/api/people${suffix}`);
    },
    get: (id: string) =>
      request<{ ok: boolean; person: Person }>(`/api/people/${encodeURIComponent(id)}`),
    create: (payload: Record<string, unknown>) =>
      request<{ ok: boolean; person: Person }>("/api/people", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    update: (id: string, payload: Record<string, unknown>) =>
      request<{ ok: boolean; person: Person }>(
        `/api/people/${encodeURIComponent(id)}`,
        { method: "PATCH", body: JSON.stringify(payload) },
      ),
    remove: (id: string, force = false) =>
      request<{ ok: boolean }>(`/api/people/${encodeURIComponent(id)}`, {
        method: "DELETE",
        body: JSON.stringify({ force }),
      }),
    checkDuplicate: (name: string, aliases?: string[]) =>
      request<{ ok: boolean; candidates: DuplicateCandidate[] }>("/api/people/check-duplicate", {
        method: "POST",
        body: JSON.stringify({ name, aliases: aliases ?? null }),
      }),
  },

  groups: {
    list: () => request<{ ok: boolean; groups: Group[] }>("/api/groups"),
    create: (name: string) =>
      request<{ ok: boolean; group: Group }>("/api/groups", {
        method: "POST",
        body: JSON.stringify({ name }),
      }),
    assign: (personId: string, groupId: string, primary: boolean) =>
      request<{ ok: boolean; person: Person }>(
        `/api/people/${encodeURIComponent(personId)}/groups`,
        {
          method: "POST",
          body: JSON.stringify({ group_id: groupId, primary }),
        },
      ),
  },

  relationships: {
    get: (perspectiveId: string, targetId: string) =>
      request<{ ok: boolean } & RelationshipResult>(
        `/api/relationships/${encodeURIComponent(perspectiveId)}/${encodeURIComponent(targetId)}`,
      ),
    from: (perspectiveId: string, domain?: string, directOnly = false) => {
      const params = new URLSearchParams();
      if (domain) params.set("domain", domain);
      if (directOnly) params.set("direct_only", "true");
      const suffix = params.toString() ? `?${params.toString()}` : "";
      return request<{
        ok: boolean;
        perspective: { id: string; name: string };
        relationships: Array<{
          target: { id: string; name: string };
          primary: RelationshipResult["primary"];
          additional: RelationshipResult["additional"];
        }>;
      }>(`/api/relationships/from/${encodeURIComponent(perspectiveId)}${suffix}`);
    },
    compare: (a: string, b: string) =>
      request<{ ok: boolean } & CompareResult>(
        `/api/compare/${encodeURIComponent(a)}/${encodeURIComponent(b)}`,
      ),
    general: {
      list: (personId?: string) => {
        const suffix = personId
          ? `?person_id=${encodeURIComponent(personId)}`
          : "";
        return request<{ ok: boolean; relationships: GeneralRelationshipFact[] }>(
          `/api/relationships/general${suffix}`,
        );
      },
      add: (payload: Record<string, unknown>) =>
        request<{ ok: boolean; relationship: GeneralRelationshipFact }>(
          "/api/relationships/general",
          { method: "POST", body: JSON.stringify(payload) },
        ),
      update: (id: number, payload: Record<string, unknown>) =>
        request<{ ok: boolean; relationship: GeneralRelationshipFact }>(
          `/api/relationships/general/${id}`,
          { method: "PATCH", body: JSON.stringify(payload) },
        ),
      remove: (id: number) =>
        request<{ ok: boolean }>(`/api/relationships/general/${id}`, {
          method: "DELETE",
        }),
    },
  },

  family: {
    diagram: (perspectiveId: string) =>
      request<{ ok: boolean; perspective_id: string; mermaid: string }>(
        `/api/family/diagram?perspective_id=${encodeURIComponent(perspectiveId)}`,
      ),
    facts: () =>
      request<{
        ok: boolean;
        people: Person[];
        parent_child: ParentChildFact[];
        marriages: MarriageFact[];
        sibling_groups: SiblingGroupFact[];
      }>("/api/family/facts"),
    addParentChild: (payload: { parent_id: string; child_id: string; role?: string; kind?: string }) =>
      request<{ ok: boolean } & ParentChildFact>("/api/family/parent-child", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    deleteParentChild: (parentId: string, childId: string) =>
      request<{ ok: boolean }>("/api/family/parent-child", {
        method: "DELETE",
        body: JSON.stringify({ parent_id: parentId, child_id: childId }),
      }),
    updateParentChild: (payload: { parent_id: string; child_id: string; role?: string; kind?: string }) =>
      request<{ ok: boolean } & ParentChildFact>("/api/family/parent-child", {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    addMarriage: (payload: { person_a: string; person_b: string; status?: string; year?: number | null; children_status?: string | null }) =>
      request<{ ok: boolean } & MarriageFact>("/api/family/marriage", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    deleteMarriage: (personA: string, personB: string) =>
      request<{ ok: boolean }>("/api/family/marriage", {
        method: "DELETE",
        body: JSON.stringify({ person_a: personA, person_b: personB }),
      }),
    updateMarriage: (payload: { person_a: string; person_b: string; status?: string; year?: number | null; children_status?: string | null }) =>
      request<{ ok: boolean } & MarriageFact>("/api/family/marriage", {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    addSiblingGroup: (memberIds: string[], type_?: string | null, ordered = false) =>
      request<{ ok: boolean; id: string; members: string[] }>("/api/family/sibling-group", {
        method: "POST",
        body: JSON.stringify({ member_ids: memberIds, type_, ordered }),
      }),
    deleteSiblingGroup: (groupId: string) =>
      request<{ ok: boolean }>(`/api/family/sibling-group/${encodeURIComponent(groupId)}`, {
        method: "DELETE",
      }),
  },

  journals: {
    get: (personId: string) =>
      request<{ ok: boolean } & Journal>(
        `/api/people/${encodeURIComponent(personId)}/journal`,
      ),
    save: (
      personId: string,
      content: string,
      expected: { modified_ns?: string | null; sha256?: string | null },
    ) =>
      request<{ ok: boolean } & Journal>(
        `/api/people/${encodeURIComponent(personId)}/journal`,
        {
          method: "PUT",
          body: JSON.stringify({
            content,
            expected_modified_ns: expected.modified_ns ?? null,
            expected_sha256: expected.sha256 ?? null,
          }),
        },
      ),
    append: (personId: string, text: string, heading?: string) =>
      request<{ ok: boolean } & Journal>(
        `/api/people/${encodeURIComponent(personId)}/journal/append`,
        {
          method: "POST",
          body: JSON.stringify({ text, heading: heading ?? null }),
        },
      ),
  },

  search: (q: string) => {
    const params = new URLSearchParams({ q });
    return request<{ ok: boolean; results: SearchResult[] }>(
      `/api/search?${params.toString()}`,
    );
  },

  dataRoot: {
    status: () => request<import("./features/dataRoot/types").DataRootStatus>("/api/data-root"),
    validate: () => request<import("./features/dataRoot/types").DataRootHealth>("/api/data-root/validate", { method: "POST" }),
    repair: () => request<{ ok: boolean; repaired: number; errors: string[] }>("/api/data-root/repair", { method: "POST" }),
    move: (destinationPath: string) =>
      request<{ ok: boolean; previous_root: string; new_root: string; safety_backup_id: string; health: import("./features/dataRoot/types").DataRootHealth }>(
        "/api/data-root/move",
        { method: "POST", body: JSON.stringify({ destination_path: destinationPath }) }
      ),
    switch: (targetPath: string) =>
      request<{ ok: boolean; active_root: string; health: import("./features/dataRoot/types").DataRootHealth }>(
        "/api/data-root/switch",
        { method: "POST", body: JSON.stringify({ target_path: targetPath }) }
      ),
    initialize: (targetPath: string, ownerName?: string) =>
      request<{ ok: boolean; active_root: string; health: import("./features/dataRoot/types").DataRootHealth }>(
        "/api/data-root/initialize",
        { method: "POST", body: JSON.stringify({ target_path: targetPath, owner_name: ownerName ?? "Mohammad Yahya Hussain" }) }
      ),
    restoreTo: (backupPath: string, targetPath?: string) =>
      request<{ ok: boolean; active_root: string; health: import("./features/dataRoot/types").DataRootHealth }>(
        "/api/data-root/restore-to",
        { method: "POST", body: JSON.stringify({ backup_path: backupPath, target_path: targetPath ?? null }) }
      ),
  },

  backups: {
    list: () => request<{ ok: boolean; backups: BackupInfo[] }>("/api/backups"),
    create: (label?: string) =>
      request<{ ok: boolean; backup: BackupInfo & { files: number } }>("/api/backups", {
        method: "POST",
        body: JSON.stringify({ label: label ?? null }),
      }),
    details: (name: string) =>
      request<Record<string, unknown>>(`/api/backups/${encodeURIComponent(name)}`),
    verify: (name: string) =>
      request<{
        ok: boolean;
        name: string;
        ok_backup: boolean;
        problems: string[];
        files_checked: number;
        status?: string;
        issues?: string[];
      }>(`/api/backups/${encodeURIComponent(name)}/verify`, { method: "POST" }),
    restore: (name: string, confirmationToken: string = "RESTORE") =>
      request<{
        ok: boolean;
        restored_backup_id: string;
        safety_backup_id: string;
        post_restore_health: import("./features/dataRoot/types").DataRootHealth;
      }>(`/api/backups/${encodeURIComponent(name)}/restore`, {
        method: "POST",
        body: JSON.stringify({ confirmation_token: confirmationToken }),
      }),
  },

  hermes: {
    tools: () =>
      request<{ ok: boolean; tools: HermesToolDef[] }>("/api/hermes/tools"),
    run: (tool: string, arguments_: Record<string, unknown>) =>
      request<Record<string, unknown>>("/api/hermes/run", {
        method: "POST",
        body: JSON.stringify({ tool, arguments: arguments_ }),
      }),
  },
};
