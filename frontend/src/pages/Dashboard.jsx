import { useQuery } from '@tanstack/react-query'
import { fetchFleetSummary, triggerEtl } from '../api'
import { useState } from 'react'

function StatCard({ label, value, sub, color = 'text-white' }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <p className="text-gray-400 text-sm mb-1">{label}</p>
      <p className={`text-3xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-gray-500 text-xs mt-1">{sub}</p>}
    </div>
  )
}

export default function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['fleet-summary'],
    queryFn: fetchFleetSummary,
  })

  const [etlStatus, setEtlStatus] = useState(null)
  const [running, setRunning] = useState(false)

  async function handleEtl() {
    setRunning(true)
    setEtlStatus(null)
    try {
      const result = await triggerEtl()
      setEtlStatus(`Done — ${result.stations_processed} stations processed`)
    } catch {
      setEtlStatus('ETL failed — check backend logs')
    } finally {
      setRunning(false)
    }
  }

  if (isLoading) return <p className="text-gray-400">Loading fleet summary...</p>
  if (error) return <p className="text-red-400">Failed to load summary. Is the backend running?</p>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Fleet Dashboard</h1>
        <div className="flex items-center gap-3">
          {etlStatus && <span className="text-sm text-gray-400">{etlStatus}</span>}
          <button
            onClick={handleEtl}
            disabled={running}
            className="bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors"
          >
            {running ? 'Running ETL...' : 'Run ETL Now'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Stations" value={data.total_stations.toLocaleString()} />
        <StatCard
          label="Open Stations"
          value={data.open_stations.toLocaleString()}
          color="text-green-400"
        />
        <StatCard
          label="Temporarily Closed"
          value={data.closed_stations.toLocaleString()}
          color="text-yellow-400"
        />
        <StatCard
          label="Fleet Uptime Rate"
          value={`${(data.fleet_uptime_rate * 100).toFixed(1)}%`}
          color={data.fleet_uptime_rate > 0.9 ? 'text-green-400' : 'text-yellow-400'}
        />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Avg Availability Score"
          value={data.fleet_avg_availability_score.toFixed(1)}
          sub="out of 100"
        />
        <StatCard
          label="Avg MTBF"
          value={`${data.fleet_avg_mtbf_hours.toFixed(0)}h`}
          sub="mean time between failures"
        />
        <StatCard
          label="Open Alerts"
          value={data.open_anomaly_alerts}
          color={data.open_anomaly_alerts > 0 ? 'text-red-400' : 'text-green-400'}
        />
        <StatCard
          label="High Severity Alerts"
          value={data.high_severity_alerts}
          color={data.high_severity_alerts > 0 ? 'text-red-500' : 'text-green-400'}
        />
      </div>
    </div>
  )
}
