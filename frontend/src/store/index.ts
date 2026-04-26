import { create } from 'zustand'

export interface Container {
  id: string
  name: string
  status: string
  image: string
}

export interface LogLine {
  container: string
  level: 'info' | 'warning' | 'error'
  text: string
  ts: string
}

export interface ProposedAction {
  label: string
  action_type: 'docker_restart' | 'docker_exec'
  command: string | null
  container_name: string
}

export interface PlanStep {
  step: string
  description: string
}

export interface Plan {
  id: string
  finding_id: string
  created_at: string
  steps: PlanStep[]
  proposed_actions: ProposedAction[]
  status: string
}

export interface Finding {
  id: string
  container_name: string
  detected_at: string
  severity: 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'
  summary: string
  root_cause: string | null
  raw_logs: string
  status: 'open' | 'resolved' | 'dismissed'
  plan?: Plan | null
}

export interface AuditEntry {
  id: string
  timestamp: string
  event_type: string
  container_name: string | null
  action: string | null
  result: string | null
  details: string | null
}

export interface ActionUpdate {
  plan_id: string
  action_index: number
  status: 'executing' | 'done' | 'failed'
  output?: string
  label?: string
}

const LOG_BUFFER = 500

interface State {
  containers: Container[]
  logs: LogLine[]
  findings: Finding[]
  auditLog: AuditEntry[]
  selectedContainer: string | null
  activeFindingId: string | null
  activeTab: 'logs' | 'findings' | 'audit'
  sidebarFilter: 'all' | 'unhealthy'
  wsConnected: boolean
  actionUpdates: Record<string, ActionUpdate>

  setContainers: (containers: Container[]) => void
  addLog: (log: LogLine) => void
  addFinding: (finding: Finding) => void
  updateFinding: (id: string, updates: Partial<Finding>) => void
  attachPlan: (plan: Plan) => void
  addAuditEntry: (entry: AuditEntry) => void
  setSelectedContainer: (name: string | null) => void
  setActiveFinding: (id: string | null) => void
  setActiveTab: (tab: 'logs' | 'findings' | 'audit') => void
  setSidebarFilter: (f: 'all' | 'unhealthy') => void
  setWsConnected: (v: boolean) => void
  setActionUpdate: (update: ActionUpdate) => void
}

export const useStore = create<State>((set) => ({
  containers: [],
  logs: [],
  findings: [],
  auditLog: [],
  selectedContainer: null,
  activeFindingId: null,
  activeTab: 'logs',
  sidebarFilter: 'all',
  wsConnected: false,
  actionUpdates: {},

  setContainers: (containers) => set({ containers }),

  addLog: (log) =>
    set((s) => ({
      logs: s.logs.length >= LOG_BUFFER
        ? [...s.logs.slice(-LOG_BUFFER + 1), log]
        : [...s.logs, log],
    })),

  addFinding: (finding) =>
    set((s) => ({
      findings: [finding, ...s.findings.filter((f) => f.id !== finding.id)],
      activeFindingId: s.activeFindingId ?? finding.id,
    })),

  updateFinding: (id, updates) =>
    set((s) => ({
      findings: s.findings.map((f) => (f.id === id ? { ...f, ...updates } : f)),
    })),

  attachPlan: (plan) =>
    set((s) => ({
      findings: s.findings.map((f) =>
        f.id === plan.finding_id ? { ...f, plan } : f,
      ),
    })),

  addAuditEntry: (entry) =>
    set((s) => ({ auditLog: [entry, ...s.auditLog].slice(0, 200) })),

  setSelectedContainer: (name) => set({ selectedContainer: name }),
  setActiveFinding: (id) => set({ activeFindingId: id }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  setSidebarFilter: (sidebarFilter) => set({ sidebarFilter }),
  setWsConnected: (wsConnected) => set({ wsConnected }),
  setActionUpdate: (update) =>
    set((s) => ({
      actionUpdates: {
        ...s.actionUpdates,
        [`${update.plan_id}:${update.action_index}`]: update,
      },
    })),
}))
