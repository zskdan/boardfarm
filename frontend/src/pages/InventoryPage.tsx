import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { MapPin, Plus, RefreshCw, Settings } from 'lucide-react';
import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { bookBoard, listBoards } from '../api/client';
import StatusBadge from '../components/StatusBadge';
import ToolBadge from '../components/ToolBadge';
import { useStatusSocket } from '../hooks/useStatusSocket';

type Filter = 'all' | 'free' | 'booked' | 'offline';

const DURATIONS = [1, 2, 4, 8, 12, 24];

function QuickBook({ boardId, boardName }: { boardId: string; boardName: string }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [hours, setHours] = useState(4);
  const ref = useRef<HTMLDivElement>(null);

  const mut = useMutation({
    mutationFn: () => bookBoard(boardId, hours),
    onSuccess: (booking) => {
      qc.invalidateQueries({ queryKey: ['boards'] });
      navigate(`/boards/${boardId}`);
    },
  });

  if (!open) {
    return (
      <button
        onClick={(e) => { e.preventDefault(); setOpen(true); }}
        className="px-3 py-1 text-xs rounded-lg bg-blue-600 text-white hover:bg-blue-700 whitespace-nowrap"
      >
        Book
      </button>
    );
  }

  return (
    <div ref={ref} className="flex items-center gap-1.5">
      <select
        className="border rounded px-1.5 py-1 text-xs"
        value={hours}
        onChange={(e) => setHours(Number(e.target.value))}
        autoFocus
      >
        {DURATIONS.map((h) => (
          <option key={h} value={h}>{h}h</option>
        ))}
      </select>
      <button
        onClick={() => mut.mutate()}
        disabled={mut.isPending}
        className="px-2.5 py-1 text-xs rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 whitespace-nowrap"
      >
        {mut.isPending ? '…' : 'Confirm'}
      </button>
      <button
        onClick={() => setOpen(false)}
        className="px-2 py-1 text-xs text-gray-400 hover:text-gray-600"
      >
        ✕
      </button>
      {mut.isError && (
        <span className="text-xs text-red-500">
          {(mut.error as Error).message}
        </span>
      )}
    </div>
  );
}

type Filter2 = 'all' | 'free' | 'booked' | 'offline';

export default function InventoryPage() {
  const [filter, setFilter] = useState<Filter>('all');
  const [search, setSearch] = useState('');

  useStatusSocket();

  const { data: boards = [], isLoading, refetch, isFetching, isError } = useQuery({
    queryKey: ['boards'],
    queryFn: listBoards,
    refetchInterval: 15_000,
  });

  const filtered = boards.filter((b) => {
    const matchSearch =
      !search ||
      b.name.toLowerCase().includes(search.toLowerCase()) ||
      b.location.toLowerCase().includes(search.toLowerCase()) ||
      b.description.toLowerCase().includes(search.toLowerCase()) ||
      (b.active_booking?.username ?? '').toLowerCase().includes(search.toLowerCase());

    const matchFilter =
      filter === 'all' ||
      (filter === 'free' && b.agent_online && !b.active_booking && b.enabled) ||
      (filter === 'booked' && !!b.active_booking) ||
      (filter === 'offline' && (!b.agent_online || !b.enabled));

    return matchSearch && matchFilter;
  });

  const isFree = (b: (typeof boards)[0]) =>
    b.enabled && b.agent_online && !b.active_booking;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Board Inventory</h1>
            <p className="text-sm text-gray-500">{boards.length} boards registered</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => refetch()}
              className="p-2 rounded-lg border bg-white hover:bg-gray-50"
              title="Refresh"
            >
              <RefreshCw size={16} className={isFetching ? 'animate-spin' : ''} />
            </button>
            <Link
              to="/admin"
              className="flex items-center gap-1 px-3 py-2 rounded-lg border bg-white hover:bg-gray-50 text-sm"
            >
              <Settings size={14} /> Admin
            </Link>
            <Link
              to="/admin/new-board"
              className="flex items-center gap-1 px-3 py-2 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700"
            >
              <Plus size={14} /> Add Board
            </Link>
          </div>
        </div>

        {/* Filters */}
        <div className="flex gap-2 mb-4 flex-wrap">
          <input
            className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 flex-1 min-w-[160px] bg-white"
            placeholder="Search boards or users…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {(['all', 'free', 'booked', 'offline'] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 text-sm rounded-lg capitalize ${
                filter === f
                  ? 'bg-blue-600 text-white'
                  : 'bg-white border text-gray-600 hover:bg-gray-50'
              }`}
            >
              {f}
            </button>
          ))}
        </div>

        {/* Offline indicator */}
        {isError && (
          <div className="mb-4 px-4 py-2 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
            Cannot reach server. Retrying…
          </div>
        )}

        {/* Table */}
        {isLoading ? (
          <div className="text-center text-gray-400 py-20">Loading…</div>
        ) : filtered.length === 0 ? (
          <div className="text-center text-gray-400 py-20">No boards found</div>
        ) : (
          <div className="bg-white rounded-xl border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Board</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Status</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Booked by</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Location</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Tools</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map((b) => (
                  <tr
                    key={b.id}
                    className={`hover:bg-gray-50 transition-colors ${!b.enabled ? 'opacity-50' : ''}`}
                  >
                    <td className="px-4 py-3">
                      <Link
                        to={`/boards/${b.id}`}
                        className="font-medium text-gray-900 hover:text-blue-600 hover:underline"
                      >
                        {b.name}
                      </Link>
                      {b.description && (
                        <p className="text-xs text-gray-400 mt-0.5 max-w-xs truncate">{b.description}</p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge
                        agentOnline={b.agent_online}
                        activeBooking={!!b.active_booking}
                        enabled={b.enabled}
                      />
                    </td>
                    <td className="px-4 py-3">
                      {b.active_booking ? (
                        <span className="font-medium text-gray-800">{b.active_booking.username}</span>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {b.location ? (
                        <div className="flex items-center gap-1 text-xs text-gray-500">
                          <MapPin size={11} className="flex-shrink-0" />
                          {b.location}
                        </div>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {b.tools.map((t) => (
                          <ToolBadge key={t.id} tool={t} />
                        ))}
                        {b.tools.length === 0 && <span className="text-gray-300">—</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      {isFree(b) && (
                        <QuickBook boardId={b.id} boardName={b.name} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* History link */}
        <div className="mt-6 text-center">
          <Link to="/history" className="text-sm text-blue-600 hover:underline">
            View booking history →
          </Link>
        </div>
      </div>
    </div>
  );
}
