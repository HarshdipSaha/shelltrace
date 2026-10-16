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
  let parsedJson = true;
  try {
    payload = responseText ? JSON.parse(responseText) : null;
  } catch {
    payload = responseText;
    parsedJson = false;
  }

  if (!response.ok) {
    // A non-JSON error body (an HTML 404 from a static host with no backend behind /api, a proxy error page)
    // is never shown verbatim: it is unreadable and unsafe to echo into the page.
    if (!parsedJson) {
      const reachability = response.status === 404 || response.status >= 502
        ? 'the ShellTrace API is not reachable at this address (the backend may not be running or deployed)'
        : 'the server returned an unreadable error response';
      throw new Error(`API ${response.status}: ${reachability}`);
    }
    const detail = payload && typeof payload === 'object'
      ? payload.detail ?? JSON.stringify(payload)
      : payload || response.statusText;
    throw new Error(`API ${response.status}: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`);
  }

  if (!parsedJson) {
    throw new Error(`API ${response.status}: the server returned a response that is not valid JSON`);
  }

  return payload;
}

const jsonBody = (body) => ({ method: 'POST', body: JSON.stringify(body) });
const query = (params) => new URLSearchParams(params).toString();

export const searchEntities = (workspace, q, limit = 8) => request(
  `/entities/search?${query({ workspace, q, limit })}`,
);

// A case response without these fields would crash the case views, so reject it at the boundary.
const requireCase = (payload) => {
  const valid = payload && typeof payload === 'object' && typeof payload.case_id === 'string'
    && payload.entity && typeof payload.entity === 'object' && Array.isArray(payload.steps)
    && Array.isArray(payload.rulepacks) && payload.packs && payload.bounds;
  if (!valid) throw new Error('API returned an incomplete case response; no verdict can be shown.');
  return payload;
};

export const openCase = (body) => request('/cases', jsonBody(body)).then(requireCase);

export const getCase = (workspace, id) => request(
  `/cases/${encodeURIComponent(id)}?${query({ workspace })}`,
).then(requireCase);

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

export const judgeAlias = (workspace, aId, bId) => request(
  `/aliases/judge?${query({ workspace })}`,
  jsonBody({ a_id: aId, b_id: bId }),
);

export const subgraph = (workspace, entityId, depth = 1, limit = 50) => request(
  `/subgraph?${query({ workspace, entity_id: entityId, depth, limit })}`,
);

export const evalLatest = () => request('/eval/latest');

export const health = () => request('/health');
