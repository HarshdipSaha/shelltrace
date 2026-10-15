async function request(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  });

  const responseText = await response.text();
  let payload;
  try {
    payload = responseText ? JSON.parse(responseText) : null;
  } catch {
    payload = responseText;
  }

  if (!response.ok) {
    const detail = payload && typeof payload === 'object'
      ? payload.detail ?? JSON.stringify(payload)
      : payload || response.statusText;
    throw new Error(`API ${response.status}: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`);
  }

  return payload;
}

const jsonBody = (body) => ({ method: 'POST', body: JSON.stringify(body) });
const query = (params) => new URLSearchParams(params).toString();

export const searchEntities = (workspace, q, limit = 8) => request(
  `/entities/search?${query({ workspace, q, limit })}`,
);

export const openCase = (body) => request('/cases', jsonBody(body));

export const getCase = (workspace, id) => request(
  `/cases/${encodeURIComponent(id)}?${query({ workspace })}`,
);

export const review = (workspace, id, body) => request(
  `/cases/${encodeURIComponent(id)}/review?${query({ workspace })}`,
  jsonBody(body),
);

export const getReviews = (workspace, id) => request(
  `/cases/${encodeURIComponent(id)}/reviews?${query({ workspace })}`,
);

export const draftReport = (workspace, id) => request(
  `/cases/${encodeURIComponent(id)}/report?${query({ workspace })}`,
  { method: 'POST' },
);

export const setWatch = (workspace, id, active) => request(
  `/cases/${encodeURIComponent(id)}/watch?${query({ workspace })}`,
  jsonBody({ active }),
);

export const injectDesignation = (body) => request('/events/designation', jsonBody(body));

export const notifications = (workspace) => request(
  `/notifications?${query({ workspace })}`,
);

export const screenName = (body) => request('/screen/name', jsonBody(body));

export const decideAlias = (workspace, body) => request(
  `/aliases/decide?${query({ workspace })}`,
  jsonBody(body),
);

export const subgraph = (workspace, entityId, depth = 1, limit = 50) => request(
  `/subgraph?${query({ workspace, entity_id: entityId, depth, limit })}`,
);

export const evalLatest = () => request('/eval/latest');

export const health = () => request('/health');
