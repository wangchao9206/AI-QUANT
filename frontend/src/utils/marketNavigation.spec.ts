import {describe, expect, it} from 'vitest'
import {instrumentRoot} from './marketNavigation'

// Snapshot of the 87 product roots in CORE_FUTURES_SYMBOLS, 2026-10-20.
// Keep this fixture inside the frontend Docker build context.
const roots = 'A AD AG AL AO AP AU B BB BC BR BU BZ C CF CJ CS CU CY EB EC EG FB FG FU HC I IC IF IH IM J JD JM JR L LC LG LH LU M MA NI NR OI OP P PB PD PF PG PK PL PM PP PR PS PT PX RB RI RM RR RS RU SA SC SF SH SI SM SN SP SR SS T TA TF TL TS UR V WH WR Y ZC ZN'.split(' ')

describe('instrument identity across the product catalog', () => {
  it('covers the maintained domestic product universe', () => {
    expect(roots.length).toBe(87)
    expect(roots).toContain('JM')
  })
  it.each(roots)('keeps %s across main, historical, and delivery identifiers', root => {
    for (const symbol of [`${root}M`, `${root}0`, `${root}2701`, `${root}701`]) {
      expect(instrumentRoot(symbol)).toBe(root)
    }
  })
})
