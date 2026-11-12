const BASE_URL = 'http://localhost:8000/api/v1/monitors';

async function fetchJson(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (res.status === 204) {
    return null;
  }

  if (!res.ok) {
    const errorBody = await res.text();
    let detail = `HTTP ${res.status}`;
    try {
      const parsed = JSON.parse(errorBody);
      detail = parsed.detail || detail;
    } catch {
      detail = errorBody || detail;
    }
    throw new Error(detail);
  }

  return res.json();
}

export const api = {
  // Platform-wide
  getOverview: () => fetchJson('/overview'),
  getActiveIncidents: () => fetchJson('/incidents/active'),
  getRecentAnomalies: (limit = 50) => fetchJson(`/anomalies/recent?limit=${limit}`),

  // Monitors
  getMonitors: () => fetchJson('/'),
  createMonitor: (payload) =>
    fetchJson('/', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteMonitor: (id) =>
    fetchJson(`/${id}`, {
      method: 'DELETE',
    }),
  probeMonitor: (id) =>
    fetchJson(`/${id}/probe`, {
      method: 'POST',
    }),

  // Per-Monitor Metrics & Telemetry
  getMonitorMetrics: (id, windowHours = 24) =>
    fetchJson(`/${id}/metrics?window_hours=${windowHours}`),
  getMonitorTimeseries: (id, windowHours = 1, bucketMinutes = 1) =>
    fetchJson(`/${id}/timeseries?window_hours=${windowHours}&bucket_minutes=${bucketMinutes}`),
  getMonitorLogs: (id, limit = 50) =>
    fetchJson(`/${id}/logs?limit=${limit}`),
  getMonitorIncidents: (id) =>
    fetchJson(`/${id}/incidents`),
  getMonitorAnomalies: (id, limit = 50) =>
    fetchJson(`/${id}/anomalies?limit=${limit}`),

  // AI Root-Cause Analysis
  analyzeIncident: (incidentId) =>
    fetchJson(`/incidents/${incidentId}/analyze`, {
      method: 'POST',
    }),
};

