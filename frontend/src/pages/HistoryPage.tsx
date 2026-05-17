import { useQuery } from '@tanstack/react-query';
import { ArrowLeft } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { listBookings } from '../api/client';

function duration(start: string, end: string): string {
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function ReleaseTag({ reason }: { reason: string }) {
  const labels: Record<string, string> = {
    expired: 'Expired',
    manual: 'Released',
    admin: 'Admin release',
    '': 'Active',
  };
  const colors: Record<string, string> = {
    expired: 'bg-yellow-100 text-yellow-700',
    manual: 'bg-green-100 text-green-700',
    admin: 'bg-red-100 text-red-700',
    '': 'bg-blue-100 text-blue-700',
  };
  return (
    <span
      className={`px-2 py-0.5 text-xs rounded-full ${colors[reason] ?? 'bg-gray-100 text-gray-600'}`}
    >
      {labels[reason] ?? reason}
    </span>
  );
}

export default function HistoryPage() {
  const [filterActive, setFilterActive] = useState<boolean | undefined>(undefined);
  const [username, setUsername] = useState('');

  const { data: bookings = [], isLoading } = useQuery({
    queryKey: ['bookings', filterActive, username],
    queryFn: () =>
      listBookings({
        active: filterActive,
        username: username || undefined,
        limit: 100,
      }),
  });

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto px-4 py-6">
        <Link
          to="/boards"
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 mb-4"
        >
          <ArrowLeft size={14} /> Back to inventory
        </Link>
        <h1 className="text-2xl font-bold text-gray-900 mb-4">Booking History</h1>

        {/* Filters */}
        <div className="flex gap-2 mb-4 flex-wrap">
          <input
            className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Filter by user…"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          {([
            ['All', undefined],
            ['Active', true],
            ['Past', false],
          ] as [string, boolean | undefined][]).map(([label, val]) => (
            <button
              key={label}
              onClick={() => setFilterActive(val)}
              className={`px-3 py-1.5 text-sm rounded-lg ${
                filterActive === val
                  ? 'bg-blue-600 text-white'
                  : 'bg-white border text-gray-600 hover:bg-gray-50'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="text-center text-gray-400 py-20">Loading…</div>
        ) : bookings.length === 0 ? (
          <div className="text-center text-gray-400 py-20">No bookings found</div>
        ) : (
          <div className="bg-white rounded-xl border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  {['Board', 'User', 'Start', 'Duration', 'Status'].map((h) => (
                    <th
                      key={h}
                      className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y">
                {bookings.map((bk) => (
                  <tr key={bk.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-800">
                      <Link
                        to={`/boards/${bk.board_id}`}
                        className="hover:underline"
                      >
                        {bk.board_name || bk.board_id}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-gray-600">{bk.username}</td>
                    <td className="px-4 py-3 text-gray-500">
                      {new Date(bk.start_time).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {duration(bk.start_time, bk.end_time)}
                      {bk.extended && (
                        <span className="ml-1 text-xs text-gray-400">(+ext)</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <ReleaseTag reason={bk.active ? '' : bk.release_reason} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
