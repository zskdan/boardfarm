import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { MapPin, Plus, RefreshCw, Settings, X } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { bookBoard, listBoards } from '../api/client';
import type { BoardInfo } from '../api/types';
import StatusBadge from '../components/StatusBadge';
import ToolBadge from '../components/ToolBadge';
import { useStatusSocket } from '../hooks/useStatusSocket';

type Filter = 'all' | 'free' | 'booked' | 'offline';

// ── Book modal ────────────────────────────────────────────────────────────────

function BookModal({ board, onClose }: { board: BoardInfo; onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [hours, setHours] = useState(4);
  const [comment, setComment] = useState('');

  const mut = useMutation({
    mutationFn: () => bookBoard(board.id, hours, comment),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['boards'] });
      onClose();
      navigate(`/boards/${board.id}`);
    },
  });

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Book board</h2>
            <p className="text-sm text-gray-500 mt-0.5">{board.name}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 mt-0.5">
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-gray-600">Duration (hours)</span>
            <input
              type="number"
              min={1}
              max={24}
              value={hours}
              onChange={(e) => setHours(Math.min(24, Math.max(1, Number(e.target.value))))}
              className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <span className="text-xs text-gray-400">Maximum 24 hours · extendable once after booking</span>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-gray-600">Comment <span className="text-gray-400 font-normal">(optional)</span></span>
            <textarea
              rows={3}
              maxLength={500}
              placeholder="What are you using this board for?"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
          </label>

          {mut.isError && (
            <p className="text-xs text-red-600">{(mut.error as Error).message}</p>
          )}

          <div className="flex gap-2 justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm border rounded-lg hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={() => mut.mutate()}
              disabled={mut.isPending}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {mut.isPending ? 'Booking…' : `Book for ${hours}h`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function InventoryPage() {
  const [filter, setFilter] = useState<Filter>('all');
  const [search, setSearch] = useState('');
  const [bookingBoard, setBookingBoard] = useState<BoardInfo | null>(null);

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

  const isFree = (b: BoardInfo) => b.enabled && b.agent_online && !b.active_booking;

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
                        <div>
                          <span className="font-medium text-gray-800">{b.active_booking.username}</span>
                          {b.active_booking.comment && (
                            <p className="text-xs text-gray-400 mt-0.5 max-w-[160px] truncate" title={b.active_booking.comment}>
                              {b.active_booking.comment}
                            </p>
                          )}
                        </div>
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
                    <td className="px-4 py-3 text-right">
                      {isFree(b) && (
                        <button
                          onClick={() => setBookingBoard(b)}
                          className="px-3 py-1 text-xs rounded-lg bg-blue-600 text-white hover:bg-blue-700 whitespace-nowrap"
                        >
                          Book
                        </button>
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

      {bookingBoard && (
        <BookModal board={bookingBoard} onClose={() => setBookingBoard(null)} />
      )}
    </div>
  );
}
