import { useQuery } from '@tanstack/react-query';
import { Plus, RefreshCw, Settings } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { listBoards } from '../api/client';
import BoardCard from '../components/BoardCard';

type Filter = 'all' | 'free' | 'booked' | 'offline';

export default function InventoryPage() {
  const [filter, setFilter] = useState<Filter>('all');
  const [search, setSearch] = useState('');

  const { data: boards = [], isLoading, refetch, isFetching } = useQuery({
    queryKey: ['boards'],
    queryFn: listBoards,
    refetchInterval: 15_000,
  });

  const filtered = boards.filter((b) => {
    const matchSearch =
      !search ||
      b.name.toLowerCase().includes(search.toLowerCase()) ||
      b.location.toLowerCase().includes(search.toLowerCase()) ||
      b.description.toLowerCase().includes(search.toLowerCase());

    const matchFilter =
      filter === 'all' ||
      (filter === 'free' && b.agent_online && !b.active_booking && b.enabled) ||
      (filter === 'booked' && !!b.active_booking) ||
      (filter === 'offline' && (!b.agent_online || !b.enabled));

    return matchSearch && matchFilter;
  });

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
            className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 flex-1 min-w-[160px]"
            placeholder="Search boards…"
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

        {/* Grid */}
        {isLoading ? (
          <div className="text-center text-gray-400 py-20">Loading…</div>
        ) : filtered.length === 0 ? (
          <div className="text-center text-gray-400 py-20">No boards found</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filtered.map((b) => (
              <BoardCard key={b.id} board={b} />
            ))}
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
