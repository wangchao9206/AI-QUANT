import http from 'k6/http'
import { check, sleep } from 'k6'
import { Rate, Trend } from 'k6/metrics'

const baseUrl = __ENV.BASE_URL || 'http://gateway-service:8080'
const symbol = __ENV.SYMBOL || 'RB2505'
const applicationErrors = new Rate('application_errors')
const gatewayLatency = new Trend('gateway_latency', true)
const historyLatency = new Trend('history_latency', true)

export const options = {
  scenarios: {
    stepped_read_load: {
      executor: 'ramping-arrival-rate',
      startRate: 10,
      timeUnit: '1s',
      preAllocatedVUs: 30,
      maxVUs: 150,
      stages: [
        { target: 25, duration: '30s' },
        { target: 75, duration: '1m' },
        { target: 120, duration: '1m' },
        { target: 0, duration: '20s' },
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.001'],
    application_errors: ['rate<0.001'],
    http_req_duration: ['p(95)<300', 'p(99)<800'],
    gateway_latency: ['p(95)<120'],
    history_latency: ['p(95)<300'],
  },
  discardResponseBodies: true,
}

export default function () {
  const traceId = `k6-${__VU}-${__ITER}`
  const params = { headers: { Accept: 'application/json', 'X-Trace-Id': traceId } }
  const health = http.get(`${baseUrl}/actuator/health`, params)
  gatewayLatency.add(health.timings.duration)
  const history = http.get(`${baseUrl}/api/v1/market/${symbol}/history?limit=120`, params)
  historyLatency.add(history.timings.duration)

  const ok = check(health, { 'gateway health is 200': (response) => response.status === 200 })
    && check(history, { 'history response is 200': (response) => response.status === 200 })
  applicationErrors.add(!ok)
  sleep(Math.random() * 0.2)
}
