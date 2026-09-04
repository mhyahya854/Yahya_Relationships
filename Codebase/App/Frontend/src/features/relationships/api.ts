import type {
  GraphNeighborsResponse,
  PathsResponse,
  RelationshipResultDto,
} from "./types";

const BASE = "";

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
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
    throw new Error(body.error?.message ?? `Request failed (${response.status})`);
  }
  return payload as T;
}

export const relationshipsApi = {
  relationship: (perspectiveId: string, targetId: string) =>
    request<RelationshipResultDto>(
      `/api/relationships/${encodeURIComponent(perspectiveId)}/${encodeURIComponent(targetId)}`,
    ),
  paths: (
    perspectiveId: string,
    targetId: string,
    maxDepth = 10,
    maxPaths = 10,
  ) =>
    request<PathsResponse>(
      `/api/relationships/${encodeURIComponent(perspectiveId)}/${encodeURIComponent(targetId)}/paths?max_depth=${maxDepth}&max_paths=${maxPaths}`,
    ),
  neighbors: (
    personId: string,
    perspectiveId: string,
    filters: string[],
  ) => {
    const params = new URLSearchParams({
      perspective_id: perspectiveId,
      filters: filters.join(","),
    });
    return request<GraphNeighborsResponse>(
      `/api/relationships/graph/neighbors/${encodeURIComponent(personId)}?${params.toString()}`,
    );
  },
  fromPerspective: (perspectiveId: string) =>
    request<{
      ok: boolean;
      perspective: { id: string; name: string };
      relationships: Array<{
        target: { id: string; name: string };
        primary: RelationshipResultDto["primary"];
        additional: RelationshipResultDto["additional"];
      }>;
    }>(`/api/relationships/from/${encodeURIComponent(perspectiveId)}`),
};
