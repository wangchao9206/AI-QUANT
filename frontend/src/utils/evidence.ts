import type { Prediction } from '../services/api'

export function evidenceSummary(prediction: Prediction) {
  const usable = prediction.dimensions.filter(d => d.includedInScore && d.score !== null && d.confidence !== null)
  const configured = prediction.dimensions.reduce((sum,d) => sum+d.weight,0)
  const available = usable.reduce((sum,d) => sum+d.weight,0)
  const culture = (prediction.culturalReferences ?? []).filter(d => d.includedInScore && d.score !== null)
    .reduce((sum,d) => sum+d.weight,0)
  return { available: usable.length, total: prediction.dimensions.length,
    coverage: configured ? available/configured : 0,
    culturalShare: available+culture ? culture/(available+culture) : 0,
    missing: prediction.dimensions.filter(d => !usable.includes(d)).map(d => d.name) }
}
