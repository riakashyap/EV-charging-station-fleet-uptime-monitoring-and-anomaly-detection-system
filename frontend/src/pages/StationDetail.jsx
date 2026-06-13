import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { fetchStation, fetchStationHealth, fetchDiagnosis } from '../api'

const CONFIDENCE_COLOR = { high: 'text-green-400', medium: 'text-yellow-400', low: 'text-gray-400' }
const SEVERITY_COLOR = { high: 'text-red-400', medium: 'text-yellow-400', low: 'text-gray-400' }
const HYPOTHESIS_LABEL = {
  network_failure: 'Network Failure',
  hardware_failure: 'Hardware Failure',
  power_supply_failure: 'Power Supply Failure',
  intermittent_unknown: 'Intermittent / Unknown',
}

function Section({ title, children }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
      <h2 className="text-gray-400 text-sm font-semibold uppercase tracking-wider">{title}</h2>
      {children}
    </div>
  )
}

function Row({ label, value, valueClass = 'text-white' }) {
  return (
    <div className="flex justify-between items-center text-sm">
      <span className="text-gray-400">{label}</span>
      <span className={`font-medium ${valueClass}`}>{value ?? '—'}</span>
    </div>
  )
}

export default function StationDetail() {
  const { nrelId } = useParams()
  const navigate = useNavigate()

  const station = useQuery({ queryKey: ['station', nrelId], queryFn: () => fetchStation(nrelId) })
  const health = useQuery({ queryKey: ['health', nrelId], queryFn: () => fetchStationHealth(nrelId) })
  const diagnosis = useQuery({ queryKey: ['diagnosis', nrelId], queryFn: () => fetchDiagnosis(nrelId) })

  if (station.isLoading) return <p className="text-gray-400">Loading station...</p>
  if (station.error) return <p className="text-red-400">Station not found.</p>

  const s = station.data
  const h = health.data
  const d = diagnosis.data

  return (
    <div className="space-y-5 max-w-3xl">
      <button onClick={() => navigate(-1)} className="text-gray-500 hover:text-white text-sm">
        ← Back
      </button>

      <h1 className="text-2xl font-bold">{s.station_name}</h1>
      <p className="text-gray-400">{s.street}, {s.city}, {s.state} {s.zip_code}</p>

      <Section title="Station Info">
        <Row label="Network" value={s.ev_network} />
        <Row label="Status" value={s.status_code === 'E' ? 'Open' : 'Temp Closed'}
          valueClass={s.status_code === 'E' ? 'text-green-400' : 'text-yellow-400'} />
        <Row label="Level 2 Ports" value={s.ev_level2_ports} />
        <Row label="DC Fast Ports" value={s.ev_dc_fast_ports} />
        <Row label="Open Date" value={s.open_date} />
        <Row label="Last Synced" value={s.last_synced ? new Date(s.last_synced).toLocaleString() : null} />
      </Section>

      {h && (
        <Section title="Health Metrics">
          <Row label="Uptime Rate" value={`${(h.uptime_rate * 100).toFixed(1)}%`}
            valueClass={h.uptime_rate > 0.9 ? 'text-green-400' : 'text-yellow-400'} />
          <Row label="Availability Score" value={`${h.availability_score} / 100`} />
          <Row label="Outage Count" value={h.outage_count} />
          <Row label="MTBF" value={`${h.mtbf_hours}h`} />
          <Row label="Last Computed" value={new Date(h.last_computed).toLocaleString()} />
        </Section>
      )}

      {d?.root_cause && (
        <Section title="Diagnostic Report">
          <Row
            label="Root Cause Hypothesis"
            value={HYPOTHESIS_LABEL[d.root_cause.hypothesis] || d.root_cause.hypothesis}
            valueClass="text-yellow-300"
          />
          <Row
            label="Confidence"
            value={d.root_cause.confidence}
            valueClass={CONFIDENCE_COLOR[d.root_cause.confidence]}
          />
          <div className="pt-2 space-y-2">
            <p className="text-gray-400 text-xs uppercase tracking-wider">Reasoning</p>
            <p className="text-sm text-gray-300">{d.root_cause.reasoning}</p>
          </div>
          <div className="pt-2 space-y-2">
            <p className="text-gray-400 text-xs uppercase tracking-wider">Recommended Action</p>
            <p className="text-sm text-green-300">{d.root_cause.recommended_action}</p>
          </div>
        </Section>
      )}

      {d?.open_alerts?.length > 0 && (
        <Section title={`Open Alerts (${d.open_alerts.length})`}>
          {d.open_alerts.map((a, i) => (
            <div key={i} className="border border-gray-800 rounded-lg p-3 space-y-1">
              <div className="flex justify-between text-xs">
                <span className="text-gray-500 uppercase">{a.type}</span>
                <span className={SEVERITY_COLOR[a.severity]}>{a.severity}</span>
              </div>
              <p className="text-sm text-gray-300">{a.message}</p>
            </div>
          ))}
        </Section>
      )}
    </div>
  )
}
