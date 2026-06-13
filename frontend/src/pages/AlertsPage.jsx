import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { fetchAlerts, resolveAlert } from '../api'

const SEVERITY_COLOR = { high: 'text-red-400', medium: 'text-yellow-400', low: 'text-gray-400' }
const SEVERITY_BG = { high: 'border-red-800', medium: 'border-yellow-800', low: 'border-gray-700' }

export default function AlertsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [severity, setSeverity] = useState('')
  const [type, setType] = useState('')

  const { data, isLoading, error } = useQuery({
    queryKey: ['alerts', severity, type],
    queryFn: () => fetchAlerts({ severity: severity || undefined, alert_type: type || undefined }),
  })

  const resolve = useMutation({
    mutationFn: resolveAlert,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alerts'] }),
  })

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Anomaly Alerts</h1>

      <div className="flex gap-3">
        <select
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-green-500"
          value={severity}
          onChange={e => setSeverity(e.target.value)}
        >
          <option value="">All Severities</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <select
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-green-500"
          value={type}
          onChange={e => setType(e.target.value)}
        >
          <option value="">All Types</option>
          <option value="zscore">Z-Score</option>
          <option value="iqr">IQR</option>
          <option value="rolling">Rolling Window</option>
        </select>
      </div>

      {isLoading && <p className="text-gray-400">Loading alerts...</p>}
      {error && <p className="text-red-400">Failed to load alerts.</p>}

      {data && (
        <>
          <p className="text-gray-500 text-sm">{data.total} open alerts</p>
          <div className="space-y-3">
            {data.alerts.length === 0 && (
              <p className="text-green-400">No alerts — fleet looks healthy.</p>
            )}
            {data.alerts.map(alert => (
              <div
                key={alert.id}
                className={`bg-gray-900 border ${SEVERITY_BG[alert.severity]} rounded-xl p-4 space-y-2`}
              >
                <div className="flex justify-between items-start">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                      <span className="uppercase">{alert.alert_type}</span>
                      <span>·</span>
                      <span className={`font-semibold ${SEVERITY_COLOR[alert.severity]}`}>
                        {alert.severity}
                      </span>
                      <span>·</span>
                      <span>{new Date(alert.detected_at).toLocaleString()}</span>
                    </div>
                    <p className="text-sm text-gray-200">{alert.message}</p>
                  </div>
                  <div className="flex gap-2 ml-4 shrink-0">
                    <button
                      onClick={() => navigate(`/stations/${alert.nrel_id}`)}
                      className="text-xs bg-gray-800 hover:bg-gray-700 px-3 py-1.5 rounded-lg transition-colors"
                    >
                      View Station
                    </button>
                    <button
                      onClick={() => resolve.mutate(alert.id)}
                      disabled={resolve.isPending}
                      className="text-xs bg-green-700 hover:bg-green-600 disabled:opacity-50 px-3 py-1.5 rounded-lg transition-colors"
                    >
                      Resolve
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
