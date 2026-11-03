export interface ChartStructureOverlay {
  id:string
  type:'FRACTAL'|'BI'|'SEGMENT'|'ZONE'|'BSP'
  startIndex:number
  endIndex:number
  startPrice?:number
  endPrice?:number
  low?:number
  high?:number
  engineConfirmed:boolean|null
  signalType?:string
  signalState?:'CANDIDATE'|'INVALIDATED'
}
