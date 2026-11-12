import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  ArrowUpRight,
  Bot,
  BrainCircuit,
  CheckCircle2,
  Clock,
  Cpu,
  Flame,
  Globe,
  Layers,
  Pause,
  Play,
  PlayCircle,
  Plus,
  RefreshCw,
  Search,
  Server,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  Trash2,
  TrendingUp,
  XCircle,
  Zap,
} from 'lucide-react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from 'recharts';
import { api } from './api';

// --- Preset Monitor Templates for Chaos Testing ---
const PRESETS = [
  {
    name: 'Chaos Health Baseline',
    url: 'http://localhost:9000/health',
    method: 'GET',
    interval_seconds: 30,
    timeout_seconds: 5.0,
    expected_status: 200,
    badge: 'Baseline',
    badgeColor: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  },
  {
    name: 'Chaos Flaky (15% Jitter)',
    url: 'http://localhost:9000/flaky',
    method: 'GET',
    interval_seconds: 15,
    timeout_seconds: 5.0,
    expected_status: 200,
    badge: 'Flaky',
    badgeColor: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  },
  {
    name: 'Chaos Latent Spike (ML Detector)',
    url: 'http://localhost:9000/latent-spike',
    method: 'GET',
    interval_seconds: 15,
    timeout_seconds: 5.0,
    expected_status: 200,
    badge: 'Anomaly',
    badgeColor: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  },
  {
    name: 'Chaos Rate Limited (429 Throttling)',
    url: 'http://localhost:9000/rate-limited',
    method: 'GET',
    interval_seconds: 15,
    timeout_seconds: 5.0,
    expected_status: 200,
    badge: 'Rate Limit',
    badgeColor: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
  },
  {
    name: 'Chaos Down (503 DB Pool Outage)',
    url: 'http://localhost:9000/down',
    method: 'GET',
    interval_seconds: 15,
    timeout_seconds: 5.0,
    expected_status: 200,
    badge: 'Outage',
    badgeColor: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
  },
];

export default function App() {
  // --- Core State ---
  const [overview, setOverview] = useState(null);
  const [monitors, setMonitors] = useState([]);
  const [selectedMonitorId, setSelectedMonitorId] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Selected monitor specific telemetry
  const [monitorMetrics, setMonitorMetrics] = useState(null);
  const [timeseries, setTimeseries] = useState([]);
  const [logs, setLogs] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [anomalies, setAnomalies] = useState([]);

  // UI state
  const [activeTab, setActiveTab] = useState('rca'); // 'rca' | 'anomalies' | 'logs'
  const [timeWindowHours, setTimeWindowHours] = useState(1);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [probingId, setProbingId] = useState(null);
  const [analyzingIncidentId, setAnalyzingIncidentId] = useState(null);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [lastSyncTime, setLastSyncTime] = useState(new Date());

  // Form State
  const [formData, setFormData] = useState({
    name: '',
    url: '',
    method: 'GET',
    interval_seconds: 30,
    timeout_seconds: 5.0,
    expected_status: 200,
  });
  const [formError, setFormError] = useState('');
  const [formSubmitting, setFormSubmitting] = useState(false);

  // Selected monitor entity
  const selectedMonitor = useMemo(
    () => monitors.find((m) => m.id === selectedMonitorId) || monitors[0] || null,
    [monitors, selectedMonitorId]
  );

  // --- Data Fetching ---
  const loadPlatformData = useCallback(async () => {
    try {
      const [ovData, monsData] = await Promise.all([
        api.getOverview().catch(() => null),
        api.getMonitors().catch(() => []),
      ]);
      if (ovData) setOverview(ovData);
      setMonitors(monsData);

      if (!selectedMonitorId && monsData.length > 0) {
        setSelectedMonitorId(monsData[0].id);
      }
      setLastSyncTime(new Date());
    } catch (err) {
      console.error('Failed to load platform data:', err);
    }
  }, [selectedMonitorId]);

  const loadMonitorTelemetry = useCallback(async (monId) => {
    if (!monId) return;
    try {
      const [metricsData, tsData, logsData, incsData, anomsData] = await Promise.all([
        api.getMonitorMetrics(monId, 24).catch(() => null),
        api.getMonitorTimeseries(monId, timeWindowHours, 1).catch(() => []),
        api.getMonitorLogs(monId, 40).catch(() => []),
        api.getMonitorIncidents(monId).catch(() => []),
        api.getMonitorAnomalies(monId, 40).catch(() => []),
      ]);
      setMonitorMetrics(metricsData);
      setTimeseries(tsData);
      setLogs(logsData);
      setIncidents(incsData);
      setAnomalies(anomsData);
    } catch (err) {
      console.error('Failed to load monitor telemetry:', err);
    }
  }, [timeWindowHours]);

  // Combined Refresh
  const handleRefreshAll = useCallback(async () => {
    setIsRefreshing(true);
    await loadPlatformData();
    if (selectedMonitor?.id) {
      await loadMonitorTelemetry(selectedMonitor.id);
    }
    setIsRefreshing(false);
  }, [loadPlatformData, loadMonitorTelemetry, selectedMonitor?.id]);

  // Initial load
  useEffect(() => {
    loadPlatformData();
  }, [loadPlatformData]);

  // Reload telemetry when selected monitor or time window changes
  useEffect(() => {
    if (selectedMonitor?.id) {
      loadMonitorTelemetry(selectedMonitor.id);
    }
  }, [selectedMonitor?.id, loadMonitorTelemetry, timeWindowHours]);

  // 10s Auto-refresh timer
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      handleRefreshAll();
    }, 10000);
    return () => clearInterval(interval);
  }, [autoRefresh, handleRefreshAll]);

  // --- Actions ---
  const handleProbeNow = async (e, monitorId) => {
    e?.stopPropagation();
    try {
      setProbingId(monitorId);
      await api.probeMonitor(monitorId);
      await handleRefreshAll();
    } catch (err) {
      alert(`Manual probe failed: ${err.message}`);
    } finally {
      setProbingId(null);
    }
  };

  const handleDeleteMonitor = async (e, monitorId, name) => {
    e?.stopPropagation();
    if (!confirm(`Delete monitor "${name}" and all historical logs?`)) return;
    try {
      await api.deleteMonitor(monitorId);
      if (selectedMonitorId === monitorId) {
        setSelectedMonitorId(null);
      }
      await handleRefreshAll();
    } catch (err) {
      alert(`Failed to delete monitor: ${err.message}`);
    }
  };

  const handleAnalyzeRCA = async (incidentId) => {
    try {
      setAnalyzingIncidentId(incidentId);
      await api.analyzeIncident(incidentId);
      if (selectedMonitor?.id) {
        const incs = await api.getMonitorIncidents(selectedMonitor.id);
        setIncidents(incs);
      }
    } catch (err) {
      alert(`Failed to analyze incident: ${err.message}`);
    } finally {
      setAnalyzingIncidentId(null);
    }
  };

  const handleCreateMonitor = async (e) => {
    e.preventDefault();
    setFormError('');
    setFormSubmitting(true);
    try {
      const created = await api.createMonitor(formData);
      setIsAddModalOpen(false);
      setFormData({
        name: '',
        url: '',
        method: 'GET',
        interval_seconds: 30,
        timeout_seconds: 5.0,
        expected_status: 200,
      });
      await loadPlatformData();
      setSelectedMonitorId(created.id);
    } catch (err) {
      setFormError(err.message);
    } finally {
      setFormSubmitting(false);
    }
  };

  const applyPreset = (preset) => {
    setFormData({
      name: preset.name,
      url: preset.url,
      method: preset.method,
      interval_seconds: preset.interval_seconds,
      timeout_seconds: preset.timeout_seconds,
      expected_status: preset.expected_status,
    });
  };

  // Filter monitors
  const filteredMonitors = useMemo(() => {
    if (!searchQuery.trim()) return monitors;
    const q = searchQuery.toLowerCase();
    return monitors.filter(
      (m) =>
        m.name.toLowerCase().includes(q) ||
        m.url.toLowerCase().includes(q) ||
        m.current_status.toLowerCase().includes(q)
    );
  }, [monitors, searchQuery]);

  // Chart data formatting
  const chartData = useMemo(() => {
    return timeseries.map((pt) => {
      const date = new Date(pt.bucket_start);
      return {
        time: date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        avg: pt.avg_latency_ms,
        p95: pt.p95_latency_ms,
        p99: pt.p99_latency_ms,
        probes: pt.probe_count,
        successRate: pt.success_rate,
      };
    });
  }, [timeseries]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* ======================================================== */}
      {/* 1. TOP ENTERPRISE HEADER BAR                            */}
      {/* ======================================================== */}
      <header className="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur-md sticky top-0 z-30 px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2.5">
            <div className="relative flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-700 shadow-lg shadow-emerald-500/20 text-white">
              <Activity className="w-5 h-5 animate-pulse" />
              <span className="absolute -top-1 -right-1 flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
              </span>
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-lg font-bold tracking-tight text-white flex items-center gap-1.5">
                  API Pulse <span className="text-emerald-400">AI</span>
                </h1>
                <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                  v1.0 SRE
                </span>
              </div>
              <p className="text-xs text-slate-400">Distributed Observability & Predictive RCA Platform</p>
            </div>
          </div>
        </div>

        {/* Header Right Controls */}
        <div className="flex items-center space-x-3 text-xs">
          {/* Sync Time */}
          <div className="hidden md:flex items-center space-x-1.5 text-slate-400 bg-slate-800/50 px-3 py-1.5 rounded-lg border border-slate-700/50">
            <Clock className="w-3.5 h-3.5 text-slate-500" />
            <span>Synced: {lastSyncTime.toLocaleTimeString()}</span>
          </div>

          {/* Auto Refresh Toggle */}
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border font-medium transition-all ${
              autoRefresh
                ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                : 'bg-slate-800/50 text-slate-400 border-slate-700/50 hover:bg-slate-800'
            }`}
            title={autoRefresh ? 'Auto-refresh active (every 10s)' : 'Auto-refresh paused'}
          >
            {autoRefresh ? (
              <>
                <Play className="w-3 h-3 fill-emerald-400 text-emerald-400" />
                <span>Auto (10s)</span>
              </>
            ) : (
              <>
                <Pause className="w-3 h-3 text-slate-400" />
                <span>Paused</span>
              </>
            )}
          </button>

          {/* Manual Refresh */}
          <button
            onClick={handleRefreshAll}
            disabled={isRefreshing}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-medium transition-all"
            title="Refresh all metrics"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-emerald-400' : ''}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>

          {/* Add Monitor Button */}
          <button
            onClick={() => setIsAddModalOpen(true)}
            className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-slate-950 font-semibold shadow-md shadow-emerald-500/20 transition-all cursor-pointer"
          >
            <Plus className="w-4 h-4 stroke-[2.5]" />
            <span>Add Monitor</span>
          </button>
        </div>
      </header>

      {/* ======================================================== */}
      {/* 2. TOP KPI CARDS (4 CARDS)                              */}
      {/* ======================================================== */}
      <section className="px-6 pt-5 pb-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Card 1: Platform 24h SLA Uptime */}
          <div className="relative overflow-hidden rounded-xl border border-slate-800/80 bg-slate-900/40 p-4 backdrop-blur-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-400">Platform 24h SLA Uptime</span>
              <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
                <ShieldCheck className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-2 flex items-baseline space-x-2">
              <span className="text-2xl font-bold tracking-tight text-white">
                {overview ? `${overview.overall_uptime_24h.toFixed(2)}%` : '---'}
              </span>
              <span className="text-xs font-semibold text-emerald-400 flex items-center">
                <ArrowUpRight className="w-3 h-3 mr-0.5" /> High Availability
              </span>
            </div>
            <div className="mt-3 w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-gradient-to-r from-emerald-500 to-teal-400 h-1.5 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(overview?.overall_uptime_24h || 100, 100)}%` }}
              ></div>
            </div>
          </div>

          {/* Card 2: Monitored Endpoints Breakdown */}
          <div className="relative overflow-hidden rounded-xl border border-slate-800/80 bg-slate-900/40 p-4 backdrop-blur-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-400">Active Endpoints</span>
              <div className="p-2 rounded-lg bg-teal-500/10 text-teal-400">
                <Server className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-2 flex items-baseline space-x-2">
              <span className="text-2xl font-bold tracking-tight text-white">
                {overview ? overview.total_monitors : monitors.length}
              </span>
              <span className="text-xs text-slate-400">Registered Probes</span>
            </div>
            <div className="mt-3 flex items-center space-x-2 text-[11px]">
              <span className="px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-400 font-semibold border border-emerald-500/20">
                {overview?.healthy_monitors ?? 0} Healthy
              </span>
              <span className="px-2 py-0.5 rounded-md bg-amber-500/15 text-amber-400 font-semibold border border-amber-500/20">
                {overview?.degraded_monitors ?? 0} Degraded
              </span>
              <span className="px-2 py-0.5 rounded-md bg-rose-500/15 text-rose-400 font-semibold border border-rose-500/20">
                {overview?.down_monitors ?? 0} Down
              </span>
            </div>
          </div>

          {/* Card 3: Active Incidents (3-Strike + Cooldown) */}
          <div className="relative overflow-hidden rounded-xl border border-slate-800/80 bg-slate-900/40 p-4 backdrop-blur-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-400">Active Outages</span>
              <div className="p-2 rounded-lg bg-rose-500/10 text-rose-400">
                <ShieldAlert className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-2 flex items-baseline space-x-2">
              <span className="text-2xl font-bold tracking-tight text-white">
                {overview ? overview.open_incidents_count : 0}
              </span>
              <span className="text-xs text-slate-400">Open Incidents</span>
            </div>
            <div className="mt-3 flex items-center space-x-1.5 text-[11px] text-slate-400">
              <Flame className="w-3.5 h-3.5 text-amber-400" />
              <span>3-Strike State Machine & Redis Cooldown</span>
            </div>
          </div>

          {/* Card 4: ML Anomalies 24h (Isolation Forest + Z-Score) */}
          <div className="relative overflow-hidden rounded-xl border border-slate-800/80 bg-slate-900/40 p-4 backdrop-blur-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-400">ML Anomalies (24h)</span>
              <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400">
                <BrainCircuit className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-2 flex items-baseline space-x-2">
              <span className="text-2xl font-bold tracking-tight text-purple-300">
                {overview?.anomaly_count_24h ?? 0}
              </span>
              <span className="text-xs font-semibold text-purple-400">Unsupervised IF + Z-Score</span>
            </div>
            <div className="mt-3 flex items-center space-x-1.5 text-[11px] text-slate-400">
              <Cpu className="w-3.5 h-3.5 text-purple-400" />
              <span>Async Threadpool Latency Classifier</span>
            </div>
          </div>
        </div>
      </section>

      {/* ======================================================== */}
      {/* 3. MAIN SPLIT VIEW (LEFT LIST + RIGHT DETAIL)           */}
      {/* ======================================================== */}
      <main className="flex-1 px-6 py-3 grid grid-cols-1 lg:grid-cols-12 gap-5 overflow-hidden">
        {/* ---------------------------------------------------- */}
        {/* LEFT COLUMN: MONITORS SIDEBAR (4 COLS)               */}
        {/* ---------------------------------------------------- */}
        <div className="lg:col-span-4 flex flex-col space-y-3">
          {/* Search Box */}
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search monitors by name, URL, or status..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-900/70 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/50"
            />
          </div>

          {/* Monitors Cards List */}
          <div className="flex-1 space-y-2.5 overflow-y-auto max-h-[calc(100vh-280px)] pr-1">
            {filteredMonitors.length === 0 ? (
              <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl bg-slate-900/20 p-6">
                <Globe className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                <p className="text-xs text-slate-400">No monitors match your filter.</p>
                <button
                  onClick={() => setIsAddModalOpen(true)}
                  className="mt-3 text-xs text-emerald-400 hover:text-emerald-300 font-medium"
                >
                  + Add New Monitor
                </button>
              </div>
            ) : (
              filteredMonitors.map((mon) => {
                const isSelected = selectedMonitor?.id === mon.id;
                const statusColor =
                  mon.current_status === 'HEALTHY'
                    ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400'
                    : mon.current_status === 'DEGRADED'
                    ? 'border-amber-500/40 bg-amber-500/10 text-amber-400'
                    : 'border-rose-500/40 bg-rose-500/10 text-rose-400';

                return (
                  <div
                    key={mon.id}
                    onClick={() => setSelectedMonitorId(mon.id)}
                    className={`group relative p-3.5 rounded-xl border transition-all cursor-pointer ${
                      isSelected
                        ? 'border-emerald-500/60 bg-slate-900/90 shadow-lg shadow-emerald-500/5 ring-1 ring-emerald-500/30'
                        : 'border-slate-800/80 bg-slate-900/40 hover:border-slate-700 hover:bg-slate-900/60'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="space-y-1 max-w-[70%]">
                        <div className="flex items-center space-x-2">
                          <h3 className="text-sm font-semibold text-white truncate">{mon.name}</h3>
                          <span
                            className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${statusColor}`}
                          >
                            {mon.current_status}
                          </span>
                        </div>
                        <div className="flex items-center space-x-1.5 font-mono text-[11px] text-slate-400 truncate">
                          <span className="font-bold text-slate-300">{mon.method}</span>
                          <span className="truncate">{mon.url}</span>
                        </div>
                      </div>

                      {/* Action buttons */}
                      <div className="flex items-center space-x-1">
                        <button
                          onClick={(e) => handleProbeNow(e, mon.id)}
                          disabled={probingId === mon.id}
                          className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-emerald-400 border border-slate-700/60 transition-all"
                          title="Execute on-demand probe"
                        >
                          <PlayCircle
                            className={`w-4 h-4 ${probingId === mon.id ? 'animate-spin text-emerald-400' : ''}`}
                          />
                        </button>
                        <button
                          onClick={(e) => handleDeleteMonitor(e, mon.id, mon.name)}
                          className="p-1.5 rounded-lg bg-slate-800 hover:bg-rose-950/40 text-slate-400 hover:text-rose-400 border border-slate-700/60 transition-all opacity-0 group-hover:opacity-100"
                          title="Delete monitor"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>

                    {/* Metadata Footer */}
                    <div className="mt-3 pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px] text-slate-500 font-mono">
                      <div className="flex items-center space-x-2">
                        <span>{mon.interval_seconds}s interval</span>
                        <span>•</span>
                        <span>expect {mon.expected_status}</span>
                      </div>
                      {mon.consecutive_failures > 0 && (
                        <span className="flex items-center space-x-1 text-rose-400 font-semibold">
                          <AlertTriangle className="w-3 h-3" />
                          <span>Strike {mon.consecutive_failures}/3</span>
                        </span>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* ---------------------------------------------------- */}
        {/* RIGHT COLUMN: DETAIL TELEMETRY PANEL (8 COLS)        */}
        {/* ---------------------------------------------------- */}
        <div className="lg:col-span-8 flex flex-col space-y-4 overflow-y-auto max-h-[calc(100vh-280px)] pr-1">
          {selectedMonitor ? (
            <>
              {/* Detail Header Banner */}
              <div className="p-4 rounded-xl border border-slate-800/80 bg-slate-900/40 backdrop-blur-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center space-x-2.5">
                    <h2 className="text-lg font-bold text-white tracking-tight">{selectedMonitor.name}</h2>
                    <span
                      className={`text-xs font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full border ${
                        selectedMonitor.current_status === 'HEALTHY'
                          ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400'
                          : selectedMonitor.current_status === 'DEGRADED'
                          ? 'border-amber-500/40 bg-amber-500/10 text-amber-400'
                          : 'border-rose-500/40 bg-rose-500/10 text-rose-400'
                      }`}
                    >
                      {selectedMonitor.current_status}
                    </span>
                  </div>
                  <div className="flex items-center space-x-2 text-xs font-mono text-slate-400">
                    <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-bold">
                      {selectedMonitor.method}
                    </span>
                    <span className="text-slate-300">{selectedMonitor.url}</span>
                    <span className="text-slate-600">|</span>
                    <span>Timeout: {selectedMonitor.timeout_seconds}s</span>
                  </div>
                </div>

                <div className="flex items-center space-x-2 self-start sm:self-auto">
                  <button
                    onClick={(e) => handleProbeNow(e, selectedMonitor.id)}
                    disabled={probingId === selectedMonitor.id}
                    className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 border border-emerald-500/30 font-semibold text-xs transition-all"
                  >
                    <Zap className={`w-3.5 h-3.5 ${probingId === selectedMonitor.id ? 'animate-spin' : ''}`} />
                    <span>{probingId === selectedMonitor.id ? 'Probing...' : 'Probe Now'}</span>
                  </button>
                </div>
              </div>

              {/* Percentile Metric Strip (5 Metrics) */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                <div className="p-3 rounded-xl border border-slate-800/80 bg-slate-900/30 text-center">
                  <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
                    P50 (Median)
                  </span>
                  <div className="mt-1 text-lg font-bold text-white font-mono">
                    {monitorMetrics?.p50_latency_ms !== null && monitorMetrics?.p50_latency_ms !== undefined
                      ? `${monitorMetrics.p50_latency_ms} ms`
                      : '---'}
                  </div>
                </div>

                <div className="p-3 rounded-xl border border-slate-800/80 bg-slate-900/30 text-center">
                  <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
                    P95 Latency
                  </span>
                  <div className="mt-1 text-lg font-bold text-amber-300 font-mono">
                    {monitorMetrics?.p95_latency_ms !== null && monitorMetrics?.p95_latency_ms !== undefined
                      ? `${monitorMetrics.p95_latency_ms} ms`
                      : '---'}
                  </div>
                </div>

                <div className="p-3 rounded-xl border border-slate-800/80 bg-slate-900/30 text-center">
                  <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
                    P99 (Tail)
                  </span>
                  <div className="mt-1 text-lg font-bold text-rose-400 font-mono">
                    {monitorMetrics?.p99_latency_ms !== null && monitorMetrics?.p99_latency_ms !== undefined
                      ? `${monitorMetrics.p99_latency_ms} ms`
                      : '---'}
                  </div>
                </div>

                <div className="p-3 rounded-xl border border-slate-800/80 bg-slate-900/30 text-center">
                  <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
                    Avg Latency
                  </span>
                  <div className="mt-1 text-lg font-bold text-slate-200 font-mono">
                    {monitorMetrics?.avg_latency_ms !== null && monitorMetrics?.avg_latency_ms !== undefined
                      ? `${monitorMetrics.avg_latency_ms} ms`
                      : '---'}
                  </div>
                </div>

                <div className="p-3 rounded-xl border border-slate-800/80 bg-slate-900/30 text-center col-span-2 sm:col-span-1">
                  <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
                    24h Uptime
                  </span>
                  <div className="mt-1 text-lg font-bold text-emerald-400 font-mono">
                    {monitorMetrics?.uptime_percentage !== null && monitorMetrics?.uptime_percentage !== undefined
                      ? `${monitorMetrics.uptime_percentage.toFixed(2)}%`
                      : '---'}
                  </div>
                </div>
              </div>

              {/* Interactive Recharts Timeseries Chart */}
              <div className="p-4 rounded-xl border border-slate-800/80 bg-slate-900/40 backdrop-blur-sm space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <TrendingUp className="w-4 h-4 text-emerald-400" />
                    <h3 className="text-sm font-semibold text-white">Chronological Latency Curve (Time-Series)</h3>
                  </div>

                  {/* Window Selector */}
                  <div className="flex items-center space-x-1 text-xs bg-slate-800/60 p-1 rounded-lg border border-slate-700/60">
                    {[1, 6, 24].map((hrs) => (
                      <button
                        key={hrs}
                        onClick={() => setTimeWindowHours(hrs)}
                        className={`px-2.5 py-0.5 rounded-md font-medium transition-all ${
                          timeWindowHours === hrs
                            ? 'bg-emerald-500 text-slate-950 font-bold shadow-sm'
                            : 'text-slate-400 hover:text-white'
                        }`}
                      >
                        {hrs}h
                      </button>
                    ))}
                  </div>
                </div>

                <div className="h-56 w-full pt-2">
                  {chartData.length === 0 ? (
                    <div className="h-full flex items-center justify-center text-xs text-slate-500">
                      Collecting initial time-series telemetry buckets...
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                        <defs>
                          <linearGradient id="colorAvg" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                            <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                          </linearGradient>
                          <linearGradient id="colorP95" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.4} />
                            <stop offset="95%" stopColor="#f59e0b" stopOpacity={0.0} />
                          </linearGradient>
                          <linearGradient id="colorP99" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.4} />
                            <stop offset="95%" stopColor="#f43f5e" stopOpacity={0.0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                        <XAxis dataKey="time" stroke="#64748b" tick={{ fontSize: 11 }} />
                        <YAxis stroke="#64748b" tick={{ fontSize: 11 }} unit="ms" />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#020617',
                            borderColor: '#334155',
                            borderRadius: '0.75rem',
                            fontSize: '12px',
                          }}
                        />
                        <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '8px' }} />
                        <Area
                          type="monotone"
                          dataKey="avg"
                          name="Avg (ms)"
                          stroke="#10b981"
                          strokeWidth={2}
                          fillOpacity={1}
                          fill="url(#colorAvg)"
                        />
                        <Area
                          type="monotone"
                          dataKey="p95"
                          name="P95 (ms)"
                          stroke="#f59e0b"
                          strokeWidth={2}
                          fillOpacity={1}
                          fill="url(#colorP95)"
                        />
                        <Area
                          type="monotone"
                          dataKey="p99"
                          name="P99 (ms)"
                          stroke="#f43f5e"
                          strokeWidth={2}
                          fillOpacity={1}
                          fill="url(#colorP99)"
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>

              {/* Tabbed Diagnostic Section */}
              <div className="rounded-xl border border-slate-800/80 bg-slate-900/40 backdrop-blur-sm overflow-hidden">
                {/* Tabs Header */}
                <div className="flex items-center border-b border-slate-800/80 bg-slate-900/70 px-4">
                  <button
                    onClick={() => setActiveTab('rca')}
                    className={`flex items-center space-x-2 py-3 px-4 border-b-2 text-xs font-semibold transition-all ${
                      activeTab === 'rca'
                        ? 'border-emerald-400 text-emerald-400'
                        : 'border-transparent text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Bot className="w-4 h-4" />
                    <span>AI Incident RCA Reports ({incidents.length})</span>
                  </button>

                  <button
                    onClick={() => setActiveTab('anomalies')}
                    className={`flex items-center space-x-2 py-3 px-4 border-b-2 text-xs font-semibold transition-all ${
                      activeTab === 'anomalies'
                        ? 'border-purple-400 text-purple-400'
                        : 'border-transparent text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <BrainCircuit className="w-4 h-4" />
                    <span>ML Latency Anomalies ({anomalies.length})</span>
                  </button>

                  <button
                    onClick={() => setActiveTab('logs')}
                    className={`flex items-center space-x-2 py-3 px-4 border-b-2 text-xs font-semibold transition-all ${
                      activeTab === 'logs'
                        ? 'border-teal-400 text-teal-400'
                        : 'border-transparent text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Terminal className="w-4 h-4" />
                    <span>Probe Telemetry Logs ({logs.length})</span>
                  </button>
                </div>

                {/* Tab Content Panes */}
                <div className="p-4">
                  {/* TAB 1: AI INCIDENT RCA REPORTS */}
                  {activeTab === 'rca' && (
                    <div className="space-y-4">
                      {incidents.length === 0 ? (
                        <div className="text-center py-10 text-xs text-slate-500">
                          <CheckCircle2 className="w-8 h-8 text-emerald-500/50 mx-auto mb-2" />
                          No active or historical incidents recorded for this monitor.
                        </div>
                      ) : (
                        incidents.map((inc) => (
                          <div
                            key={inc.id}
                            className="p-4 rounded-xl border border-slate-800 bg-slate-950/60 space-y-3"
                          >
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
                              <div className="flex items-center space-x-2">
                                <span
                                  className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${
                                    inc.status === 'OPEN'
                                      ? 'border-rose-500/40 bg-rose-500/10 text-rose-400'
                                      : 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400'
                                  }`}
                                >
                                  {inc.status}
                                </span>
                                <span className="text-xs font-mono text-slate-400">
                                  Started: {new Date(inc.started_at).toLocaleString()}
                                </span>
                                {inc.resolved_at && (
                                  <span className="text-xs font-mono text-emerald-400">
                                    • Resolved: {new Date(inc.resolved_at).toLocaleTimeString()}
                                  </span>
                                )}
                              </div>

                              <button
                                onClick={() => handleAnalyzeRCA(inc.id)}
                                disabled={analyzingIncidentId === inc.id}
                                className="flex items-center space-x-1.5 px-3 py-1 rounded-lg bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 border border-purple-500/30 text-xs font-medium transition-all self-start sm:self-auto"
                              >
                                <Bot
                                  className={`w-3.5 h-3.5 ${
                                    analyzingIncidentId === inc.id ? 'animate-spin' : ''
                                  }`}
                                />
                                <span>
                                  {analyzingIncidentId === inc.id ? 'Analyzing SRE...' : 'Re-Analyze RCA'}
                                </span>
                              </button>
                            </div>

                            {/* Trigger Error */}
                            <div className="text-xs font-mono text-rose-300 bg-rose-950/20 p-2.5 rounded-lg border border-rose-900/30">
                              <span className="font-bold text-rose-400">Trigger Signature: </span>
                              {inc.trigger_error || '3 consecutive failed health probes.'}
                            </div>

                            {/* RCA Report Body */}
                            {inc.rca_summary ? (
                              <div className="bg-slate-900/80 p-4 rounded-xl border border-slate-800 text-xs text-slate-300 space-y-2 font-mono whitespace-pre-wrap leading-relaxed">
                                {inc.rca_summary}
                              </div>
                            ) : (
                              <div className="text-xs text-slate-500 italic p-3 bg-slate-900/40 rounded-lg">
                                RCA summary is being generated by AI SRE agent...
                              </div>
                            )}
                          </div>
                        ))
                      )}
                    </div>
                  )}

                  {/* TAB 2: ML LATENCY ANOMALIES */}
                  {activeTab === 'anomalies' && (
                    <div className="space-y-3">
                      {anomalies.length === 0 ? (
                        <div className="text-center py-10 text-xs text-slate-500">
                          <BrainCircuit className="w-8 h-8 text-purple-500/40 mx-auto mb-2" />
                          No ML latency anomalies flagged yet. (Requires 15+ baseline samples & Z-score &ge; 2.0&sigma;)
                        </div>
                      ) : (
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-xs font-mono">
                            <thead className="text-[11px] uppercase tracking-wider text-slate-400 border-b border-slate-800">
                              <tr>
                                <th className="pb-2">Timestamp</th>
                                <th className="pb-2">Latency</th>
                                <th className="pb-2">Z-Score Severity</th>
                                <th className="pb-2">Detection Method</th>
                                <th className="pb-2">HTTP Status</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800/60">
                              {anomalies.map((anom) => (
                                <tr key={anom.id} className="hover:bg-slate-800/30">
                                  <td className="py-2.5 text-slate-400">
                                    {new Date(anom.timestamp).toLocaleTimeString()}
                                  </td>
                                  <td className="py-2.5 font-bold text-purple-300">
                                    {anom.latency_ms.toFixed(1)} ms
                                  </td>
                                  <td className="py-2.5">
                                    <span className="px-2 py-0.5 rounded-full bg-purple-500/15 text-purple-300 font-bold border border-purple-500/30">
                                      +{anom.anomaly_score}&sigma;
                                    </span>
                                  </td>
                                  <td className="py-2.5 text-slate-300">Isolation Forest + Z-Score</td>
                                  <td className="py-2.5">
                                    <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-bold">
                                      {anom.status_code || 200} OK
                                    </span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  )}

                  {/* TAB 3: LIVE PROBE TELEMETRY LOGS */}
                  {activeTab === 'logs' && (
                    <div className="space-y-3">
                      {logs.length === 0 ? (
                        <div className="text-center py-10 text-xs text-slate-500">
                          <Terminal className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                          No probe logs recorded yet.
                        </div>
                      ) : (
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-xs font-mono">
                            <thead className="text-[11px] uppercase tracking-wider text-slate-400 border-b border-slate-800">
                              <tr>
                                <th className="pb-2">Time</th>
                                <th className="pb-2">Status</th>
                                <th className="pb-2">Latency</th>
                                <th className="pb-2">Anomaly Flag</th>
                                <th className="pb-2">Diagnostics / Snippet</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800/60">
                              {logs.map((log) => {
                                const statusColor = log.is_success
                                  ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                                  : 'bg-rose-500/15 text-rose-400 border-rose-500/30';

                                return (
                                  <tr key={log.id} className="hover:bg-slate-800/30">
                                    <td className="py-2.5 text-slate-400">
                                      {new Date(log.timestamp).toLocaleTimeString()}
                                    </td>
                                    <td className="py-2.5">
                                      <span
                                        className={`px-2 py-0.5 rounded-md font-bold text-[10px] border ${statusColor}`}
                                      >
                                        {log.status_code || 'ERR'}
                                      </span>
                                    </td>
                                    <td className="py-2.5 font-semibold text-slate-200">
                                      {log.latency_ms.toFixed(1)} ms
                                    </td>
                                    <td className="py-2.5">
                                      {log.is_anomaly ? (
                                        <span className="px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 font-bold text-[10px] border border-purple-500/40">
                                          ANOMALY (+{log.anomaly_score}&sigma;)
                                        </span>
                                      ) : (
                                        <span className="text-slate-600 text-[11px]">normal</span>
                                      )}
                                    </td>
                                    <td className="py-2.5 text-slate-400 truncate max-w-xs">
                                      {log.error_message || '—'}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="h-full flex flex-col items-center justify-center p-12 border border-dashed border-slate-800 rounded-xl bg-slate-900/20 text-center">
              <Globe className="w-12 h-12 text-slate-600 mb-3" />
              <h3 className="text-sm font-semibold text-white">No Monitor Selected</h3>
              <p className="text-xs text-slate-400 mt-1 max-w-sm">
                Select a monitor from the sidebar or click "+ Add Monitor" to start monitoring health and AI diagnostics.
              </p>
            </div>
          )}
        </div>
      </main>

      {/* ======================================================== */}
      {/* 4. ADD MONITOR MODAL (WITH 1-CLICK CHAOS PRESETS)       */}
      {/* ======================================================== */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-xl rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl space-y-5 animate-in fade-in duration-150">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-2">
                <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
                  <Plus className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">Add Health Monitor</h3>
                  <p className="text-xs text-slate-400">Configure endpoint probe target and interval</p>
                </div>
              </div>
              <button
                onClick={() => setIsAddModalOpen(false)}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
              >
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            {/* 1-Click Chaos Presets */}
            <div className="space-y-2">
              <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                <Flame className="w-3.5 h-3.5 text-amber-400" />
                1-Click Chaos Presets:
              </span>
              <div className="flex flex-wrap gap-2">
                {PRESETS.map((p) => (
                  <button
                    key={p.name}
                    type="button"
                    onClick={() => applyPreset(p)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-all ${p.badgeColor} hover:brightness-125`}
                  >
                    {p.name}
                  </button>
                ))}
              </div>
            </div>

            {/* Monitor Form */}
            <form onSubmit={handleCreateMonitor} className="space-y-4 text-xs">
              {formError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300">
                  {formError}
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1 sm:col-span-2">
                  <label className="font-medium text-slate-300">Monitor Name</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Production Payment Gateway"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div className="space-y-1 sm:col-span-2">
                  <label className="font-medium text-slate-300">Target URL</label>
                  <input
                    type="url"
                    required
                    placeholder="http://localhost:9000/health"
                    value={formData.url}
                    onChange={(e) => setFormData({ ...formData, url: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 font-mono focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-slate-300">HTTP Method</label>
                  <select
                    value={formData.method}
                    onChange={(e) => setFormData({ ...formData, method: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="GET">GET</option>
                    <option value="POST">POST</option>
                    <option value="PUT">PUT</option>
                    <option value="DELETE">DELETE</option>
                    <option value="PATCH">PATCH</option>
                    <option value="HEAD">HEAD</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-slate-300">Expected Status Code</label>
                  <input
                    type="number"
                    required
                    value={formData.expected_status}
                    onChange={(e) =>
                      setFormData({ ...formData, expected_status: parseInt(e.target.value, 10) || 200 })
                    }
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 font-mono focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-slate-300">Probe Interval (seconds)</label>
                  <input
                    type="number"
                    min={5}
                    max={86400}
                    required
                    value={formData.interval_seconds}
                    onChange={(e) =>
                      setFormData({ ...formData, interval_seconds: parseInt(e.target.value, 10) || 30 })
                    }
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 font-mono focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-slate-300">Timeout (seconds)</label>
                  <input
                    type="number"
                    step="0.5"
                    min={0.5}
                    max={60}
                    required
                    value={formData.timeout_seconds}
                    onChange={(e) =>
                      setFormData({ ...formData, timeout_seconds: parseFloat(e.target.value) || 5.0 })
                    }
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 font-mono focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>

              <div className="pt-3 border-t border-slate-800 flex items-center justify-end space-x-2">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium transition-all"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={formSubmitting}
                  className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold transition-all shadow-md shadow-emerald-500/20"
                >
                  {formSubmitting ? 'Creating Monitor...' : 'Save & Start Probing'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

