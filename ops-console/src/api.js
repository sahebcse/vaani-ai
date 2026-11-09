const BASE = '';

async function apiFetch(path, token, options = {}) {
  const resp = await fetch(BASE + path, {
    ...options,
    headers: { Authorization: `Bearer ${token}`, ...(options.headers || {}) },
  });
  if (!resp.ok) {
    throw new Error(`${options.method || 'GET'} ${path} -> ${resp.status}`);
  }
  return resp.json();
}

export const listCalls = (token) => apiFetch('/v1/admin/calls', token);
export const getEvalReport = (token) => apiFetch('/v1/admin/eval-report', token);
export const listFeedback = (token) => apiFetch('/v1/admin/feedback', token);
export const runExperiment = (token, name, prompts) =>
  apiFetch('/v1/admin/experiments', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, prompts }),
  });
