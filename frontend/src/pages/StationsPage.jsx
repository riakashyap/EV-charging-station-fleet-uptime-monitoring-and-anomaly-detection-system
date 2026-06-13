import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { fetchStations } from '../api'

const STATUS_LABEL = { E: 'Open', T: 'Temp Closed', P: 'Planned' }
const STATUS_COLOR = { E: 'text-green-400', T: 'text-yellow-400', P: 'text-gray-400' }

export default function StationsPage() {
  const navigate = useNavigate()
  const [state, setState] = useState('')
  const [network, setNetwork] = useState('')
  const [offset, setOffset] = useState(0)
  const limit = 100

  const { data, isLoading, error } = useQuery({
    queryKey: ['stations', state, network, offset],
    queryFn: () => fetchStations({ state: state || undefined, network: network || undefined, limit, offset }),
  })

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Stations</h1>

      <div className="flex gap-3">
        <input
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm w-28 focus:outline-none focus:border-green-500"
          placeholder="State (CA)"
          value={state}
          onChange={e => { setState(e.target.value.toUpperCase()); setOffset(0) }}
          maxLength={2}
        />
        <input
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm w-48 focus:outline-none focus:border-green-500"
          placeholder="Network (ChargePoint)"
          value={network}
          onChange={e => { setNetwork(e.target.value); setOffset(0) }}
        />
      </div>

      {isLoading && <p className="text-gray-400">Loading stations...</p>}
      {error && <p className="text-red-400">Failed to load stations.</p>}

      {data && (
        <>
          <p className="text-gray-500 text-sm">{data.total.toLocaleString()} stations found</p>
          <div className="overflow-x-auto rounded-xl border border-gray-800">
            <table className="w-full text-sm">
              <thead className="bg-gray-900 text-gray-400 text-left">
                <tr>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">City</th>
                  <th className="px-4 py-3">State</th>
                  <th className="px-4 py-3">Network</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">L2 Ports</th>
                  <th className="px-4 py-3">DC Fast</th>
                </tr>
              </thead>
              <tbody>
                {data.stations.map(s => (
                  <tr
                    key={s.nrel_id}
                    onClick={() => navigate(`/stations/${s.nrel_id}`)}
                    className="border-t border-gray-800 hover:bg-gray-800 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 text-green-400 font-medium">{s.station_name}</td>
                    <td className="px-4 py-3 text-gray-300">{s.city}</td>
                    <td className="px-4 py-3 text-gray-300">{s.state}</td>
                    <td className="px-4 py-3 text-gray-400">{s.ev_network || '—'}</td>
                    <td className={`px-4 py-3 font-medium ${STATUS_COLOR[s.status_code]}`}>
                      {STATUS_LABEL[s.status_code] || s.status_code}
                    </td>
                    <td className="px-4 py-3 text-gray-300">{s.ev_level2_ports}</td>
                    <td className="px-4 py-3 text-gray-300">{s.ev_dc_fast_ports}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex gap-3 items-center">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(o => Math.max(0, o - limit))}
              className="bg-gray-800 hover:bg-gray-700 disabled:opacity-40 px-4 py-2 rounded-lg text-sm"
            >
              Previous
            </button>
            <span className="text-gray-500 text-sm">
              {offset + 1}–{Math.min(offset + limit, data.total)} of {data.total.toLocaleString()}
            </span>
            <button
              disabled={offset + limit >= data.total}
              onClick={() => setOffset(o => o + limit)}
              className="bg-gray-800 hover:bg-gray-700 disabled:opacity-40 px-4 py-2 rounded-lg text-sm"
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}
