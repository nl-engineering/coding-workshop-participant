const BASE = '/api/hr-copilot-service'

export async function api(path, body) {
  const res = await fetch(BASE + path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok || data.ok === false) throw new Error(data.error || data.detail || `HTTP ${res.status}`)
  return data
}

export const ROUTES = {
  READY: { label: 'T1 · Real-time answer', color: 'success', help: 'Grounded in current policy + own records, cited' },
  TRANSACTION: { label: 'T2 · Maker / checker', color: 'secondary', help: 'AI prepares, analyst approves' },
  NEEDS_APPROVAL: { label: 'T3 · Specialist', color: 'warning', help: 'Sensitive: specialist team, confidential brief' },
  KNOWLEDGE_GAP: { label: 'Knowledge gap', color: 'error', help: 'No current policy answers this' },
}
export const STATUS = {
  DRAFT_READY: 'info', PENDING_APPROVAL: 'warning', NEEDS_SME: 'error', SENT: 'success', APPLIED: 'success', REJECTED: 'default', AWAITING_EMPLOYEE: 'info',
}
