import { request } from './api'

export type ReplayReviewContext =
  | { kind:'session'; id:string }
  | { kind:'workflow'; id:string; reviewRunId:string }

export interface ReplayReviewTarget { id:string; at:string; label:string }
export const reviewActions = {
  WAIT:'不操作，继续等', OPEN_LONG:'开多', OPEN_SHORT:'开空', ADD:'加仓', CLOSE:'平仓', REDUCE:'减仓',
} as const
export type ReplayReviewAction = keyof typeof reviewActions

const observedLabels:Record<string,string>={
  NO_ACTION:'没有操作', HOLD:'继续等待', WAIT:'继续等待', WARMING:'等待行情预热',
  BUY:'买多信号', SELL:'买空信号', FLATTEN:'平仓信号', OPEN:'开仓', ADD:'加仓',
  OPEN_LONG:'开多', OPEN_SHORT:'开空', CLOSE:'平仓', TAKE_PROFIT:'减半止盈',
  REVERSAL_CLOSE:'反手前平仓', TERMINAL_CLOSE:'期末平仓',
}
export function observedReviewAction(value:string) { return observedLabels[value]??value }

export interface ReplayReviewInput {
  clientRequestId:string
  at:string
  stage:'BAR'|'FILL'
  targetId?:string
  suggestedAction:ReplayReviewAction
  reason:string
}

export interface ReplayReview extends Omit<ReplayReviewInput,'clientRequestId'> {
  id:string
  observedAction:string
  createdAt:string
  workflowId?:string|null
}

function path(context:ReplayReviewContext) {
  return `/api/v1/paper/${context.kind==='session'?'sessions/':'workflows/versions/'}${encodeURIComponent(context.id)}/replay-reviews`
}

export const replayReviewsApi = {
  list(context:ReplayReviewContext) {
    const query=context.kind==='workflow'?`?${new URLSearchParams({reviewRunId:context.reviewRunId})}`:''
    return request<ReplayReview[]>(path(context)+query)
  },
  save(context:ReplayReviewContext,input:ReplayReviewInput) {
    const payload=context.kind==='workflow'?{...input,reviewRunId:context.reviewRunId}:input
    return request<ReplayReview>(path(context),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
  },
}
