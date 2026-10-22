import { describe, expect, it } from 'vitest'
import { renderWithProviders, screen } from '../test/utils'
import type { LongTermSnapshot } from '../types/longTerm'
import { LongTermHistoryChart } from './LongTermHistoryChart'

function snapshot(recordedAt: string, score: number | null, modelVersion = 'qvm-v1'): LongTermSnapshot {
  return {
    ticker: 'kgh', name: 'KGHM', sector: null, market: 'gpw', currency: 'PLN', asOf: '2026-10-20',
    score, qualityScore: score, valueScore: score, momentumScore: score, coverage: score === null ? 0 : 100,
    eligible: score !== null, missing: [], inputs: {}, fundamentalsObservedAt: null,
    comparisonGroup: 'market', peerCount: 10, recordedAt, modelVersion,
  }
}

describe('LongTermHistoryChart', () => {
  it('waits for two usable distinct observation times, rather than inventing a past', () => {
    const { rerender } = renderWithProviders(<LongTermHistoryChart items={[
      snapshot('2026-10-22T10:00:00Z', 70), snapshot('2026-10-22T10:00:00Z', 80), snapshot('2026-10-23T10:00:00Z', null),
    ]} />)
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.getByText(/two or more distinct times/)).toBeVisible()
    rerender(<LongTermHistoryChart items={[
      snapshot('invalid', 90), snapshot('2026-02-30T10:00:00Z', 90), snapshot('2026-10-23', 90), snapshot('2026-10-22T10:00:00Z', 70),
    ]} />)
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('preserves same-day revisions, zero scores and actual elapsed observation time', () => {
    renderWithProviders(<LongTermHistoryChart items={[
      snapshot('2026-10-22T12:00:00Z', 100), snapshot('2026-10-22T10:30:00Z', 20), snapshot('2026-10-22T10:00:00Z', 0),
    ]} />)
    const chart = screen.getByRole('img', { name: 'Recorded scores over time' })
    const points = Array.from(chart.querySelectorAll('circle'))
    expect(points.map((point) => point.getAttribute('data-score'))).toEqual(['0', '20', '100'])
    expect(points.map((point) => point.getAttribute('data-recorded-at'))).toEqual(['2026-10-22T10:00:00Z', '2026-10-22T10:30:00Z', '2026-10-22T12:00:00Z'])
    const [start, middle, end] = points.map((point) => Number(point.getAttribute('cx')))
    expect((middle - start) / (end - start)).toBeCloseTo(0.25)
    expect(points[0].querySelector('title')).toHaveTextContent('2026-10-22T10:00:00Z')
    expect(points[0].querySelector('title')).toHaveTextContent('2026-10-20')
    expect(chart.querySelectorAll('polyline')).toHaveLength(1)
  })

  it('breaks the line for missing scores and model changes without dropping valid isolated points', () => {
    renderWithProviders(<LongTermHistoryChart items={[
      snapshot('2026-10-20T10:00:00Z', 20), snapshot('2026-10-21T10:00:00Z', 30),
      snapshot('2026-10-22T10:00:00Z', null), snapshot('2026-10-23T10:00:00Z', 40),
      snapshot('2026-10-24T10:00:00Z', 50, 'qvm-v2'), snapshot('2026-10-25T10:00:00Z', 60, 'qvm-v2'),
    ]} />)
    const chart = screen.getByRole('img')
    expect(chart.querySelectorAll('circle')).toHaveLength(5)
    const lines = Array.from(chart.querySelectorAll('polyline'))
    expect(lines.map((line) => line.getAttribute('data-model'))).toEqual(['qvm-v1', 'qvm-v2'])
    expect(lines.map((line) => line.getAttribute('points')!.split(' ').length)).toEqual([2, 2])
    expect(screen.getByText('Model versions: qvm-v1, qvm-v2')).toBeVisible()
  })

  it('retains exact-time revisions and explains invalid dates omitted from the plot', () => {
    renderWithProviders(<LongTermHistoryChart items={[
      snapshot('2026-10-21T10:00:00Z', 20), snapshot('2026-10-22T10:00:00Z', 50),
      snapshot('2026-10-22T10:00:00Z', 60), snapshot('invalid', 70),
    ]} />)
    expect(screen.getByRole('img').querySelectorAll('circle')).toHaveLength(3)
    expect(screen.getByText(/share an identical timestamp/)).toBeVisible()
    expect(screen.getByText(/without a valid observation time/)).toBeVisible()
  })

  it('keeps distinct archived microsecond revisions without shifting their times', () => {
    renderWithProviders(<LongTermHistoryChart items={[
      snapshot('2026-10-22T10:00:00.123456+00:00', 20), snapshot('2026-10-22T10:00:00.123457+00:00', 50),
    ]} />)
    const points = Array.from(screen.getByRole('img').querySelectorAll('circle'))
    expect(points).toHaveLength(2)
    expect(points[0].getAttribute('cx')).not.toEqual(points[1].getAttribute('cx'))
    expect(points[0].querySelector('title')).toHaveTextContent('2026-10-22T10:00:00.123456+00:00')
  })
})
