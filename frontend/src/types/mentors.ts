export interface MentorSource {id:string;publisher:string;title:string;url:string;kind:string;publishedAt:string|null;checkedAt:string;limitation:string}
export interface MentorFactor {factor:string;evidence:string;status:string;learn:string;cannotCopy:string;alternative:string}
export interface MentorProfile {
  id:string;name:string;initials:string;style:string;admission:string;identityStatus:string;liveEvidence:string;successEvidence:string;intro:string
  identityKind?:'PUBLIC_NAME'|'CONTEST_ALIAS';researchStatus?:'DOCUMENTED'|'BACKGROUND_ONLY'|'PENDING_MATCH'|'PARTIAL_RECORD';identityNotes?:string;linkedAccountId?:string;contestRecords?:MentorContestRecord[];operationIds?:string[]
  timeline:{period:string;fact:string;sourceIds:string[]}[]
  achievements:{text:string;sourceIds:string[]}[]
  quotes:{text:string;sourceId:string;context:string}[]
  methods:{title:string;body:string;sourceIds:string[];status:string}[]
  factors:MentorFactor[];ledger:{status:string;message:string;missing:string[]};learningIds:string[];sourceIds:string[]
}
export interface MentorContestRecord {recordKey:string;event:string;edition:number|null;year:number|null;group:string;scope:string;asOf:string|null;rank:number|null;accountRef:string|null;netProfit:number|null;cumulativeNetWorth:number|null;reportedDrawdownPct:number|null;sourceIds:string[];note:string}
export interface LearningTemplate {id:string;title:string;question:string;practice:string;required:string;failure:string}
export interface ContestAccount {
  id:string;alias:string;rank:number;groupLabel:string;identityStatus:string;evidenceType:string;statementStatus:string
  periodStart:string;asOf:string;sourceUrls:string[];sourceSha256:string
  reported?:Record<string,string|number>;edition?:number;year?:number
  analysis:{metrics:Record<string,number|null>;findings:string[];byBreed:{code:string;name:string;grossClosedPnl:number;winningCloseCount:number;losingCloseCount:number;reportedDealCount?:number|null;reportedDealAmount?:number|null}[];netWorth:{date:string;value:number}[];daily?:{date:string;netWorth:number|null;netProfit:number|null;reportedRiskDegree:number|null}[]}
}
export interface SettlementSnapshot {publisher?:string;fetchedAt?:string;sampling?:string;accounts:{id:string;alias:string;rank:number;sourceUrl:string;sourceUrls:string[];sourceSha256:string;rawTradesPublic:boolean;rows:Record<string,string|number|null>[];checks?:{feeSum:number;inSum:number;outSum:number;cashResidualRows:number;maxAbsCashResidual:number}}[]}
export interface MentorOperation {
  id:string;profileId:string;periodLabel:string;datePrecision:'DAY'|'MONTH'|'YEAR'|'INTERVAL'|'UNSPECIFIED';dateStart:string|null;dateEnd:string|null
  instrument:string;contractCodes:string[];market:string;action:'OPEN'|'CLOSE'|'ADD'|'REDUCE'|'HOLD'|'REVERSE'|'POSITION';direction:'LONG'|'SHORT'|'UNSPECIFIED'
  summary:string;sourceIds:string[];sourceLocator:string;sourceType:'FIRST_PERSON_RECALL'|'REGULATORY_DISCLOSURE';ownerScope:'INDIVIDUAL'|'GUIDED_TEAM'|'CONTROLLED_COMPANIES'
  price:number|null;priceLabel:string;quantity:number|null;quantityLabel:string;publishedAt:string|null;limitations:string[];researchQuestion:string;interpretation:string;validationStatus:string;executionVerified:boolean;eligibleForLedgerAnalysis:boolean
}
export interface MentorCatalog {
  version:string;definition:string;evidencePolicy:string[];sources:MentorSource[];profiles:MentorProfile[];learningTemplates:LearningTemplate[]
  summary:{profiles:number;completePersonLedgers:number;aggregateAccounts:number;quoteCount:number;contestAliases?:number;documentedProfiles?:number;pendingProfiles?:number;backgroundProfiles?:number}
  contestSnapshot:{status:string;publisher?:string;fetchedAt?:string;asOf?:string;sampling?:string;identityWarning?:string;accounts:ContestAccount[]}
  settlementSnapshot?:SettlementSnapshot
  operations?:MentorOperation[];operationPolicy?:string[]
  operationSummary?:{records:number;profiles:number;regulatoryRecords:number;recalledRecords:number;exactDayRecords:number}
  dataCoverage?:{executionRows:number;netWorthRows:number;dailyProfitRows:number;dailyRiskRows:number;breedRows:number;settlementRows:number;linkedRequestedAliases:number}
  editions:{edition:number;year:number|null;profileId:string|null;profileIds?:string[];status:string;url:string;note:string}[];generatedAt:string
}
export interface LedgerAnalysisRequest {csvText:string;sourceLabel:string;sourceUrl:string;rightsConfirmed:boolean}
export interface LedgerPair {contract:string;direction:string;openedAt:string;closedAt:string;quantity:number;entryPrice:number;exitPrice:number;grossPnl:number;fees:number;netPnl:number;holdingHours:number}
export interface LedgerAnalysis {
  sourceLabel:string;sourceUrl:string;inputSha256:string;authenticity:string;validationStatus:string
  period:{start:string;end:string};metrics:Record<string,number|null>;warnings:string[]
  byContract:{contract:string;netPnl:number;grossPnl:number;fees:number;closedLots:number}[]
  pairs:LedgerPair[];openPositions:{contract:string;direction:string;lots:number}[]
  learningChecks:{question:string;finding:string}[]
}
