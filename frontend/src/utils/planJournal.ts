import type { ResearchPlan } from '../types/research'
export interface JournalEntry {
  id: string; savedAt: string; plan: ResearchPlan
  status: 'PLANNED' | 'EXECUTED' | 'ABANDONED'; actualPnl: number | null; notes: string
}
export const JOURNAL_KEY = 'aiquant.plan-journal.v1'
export function readJournal(): JournalEntry[] {
  try {
    const rows: unknown = JSON.parse(localStorage.getItem(JOURNAL_KEY) ?? '[]')
    return Array.isArray(rows) ? rows.filter((r): r is JournalEntry => r && typeof r.id==='string' && r.plan && typeof r.plan.contract==='string' && typeof r.plan.planId==='string' && r.plan.inputs && Number.isFinite(r.plan.inputs.equity) && typeof r.savedAt==='string') : []
  } catch { return [] }
}
export function writeJournal(rows: JournalEntry[]) {
  localStorage.setItem(JOURNAL_KEY,JSON.stringify(rows))
}
export function journalEntry(plan: ResearchPlan): JournalEntry {
  return {id:plan.planId,savedAt:new Date().toISOString(),plan:JSON.parse(JSON.stringify(plan)),status:'PLANNED',actualPnl:null,notes:''}
}
