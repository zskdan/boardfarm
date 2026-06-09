import { useQuery } from '@tanstack/react-query';
import { ArrowLeft } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { listActivity } from '../api/client';
import type { ActivityEntry } from '../api/types';

type ActionGroup = 'all' | 'bookings' | 'board_changes' | 'tools';

const ACTION_BADGE: Record<string, { label: string; cls: string }> = {
  booked:        { label: 'Booked',         cls: 'bg-blue-100 text-blue-700' },
  released:      { label: 'Released',        cls: 'bg-green-100 text-green-700' },
  extended:      { label: 'Extended',        cls: 'bg-teal-100 text-teal-700' },
  board_created: { label: 'Device created',  cls: 'bg-purple-100 text-purple-700' },
  board_updated: { label: 'Device updated',  cls: 'bg-gray-100 text-gray-600' },
  board_deleted: { label: 'Device deleted',  cls: 'bg-red-100 text-red-700' },
  tool_added:    { label: 'Tool added',      cls: 'bg-orange-100 text-orange-700' },
  tool_deleted:  { label: 'Tool deleted',    cls: 'bg-red-100 text-red-700' },
};

const GROUP_ACTIONS: Record<ActionGroup, string[]> = {
  all: [],
  bookings: ['booked', 'released', 'extended'],
  board_changes: ['board_created', 'board_updated', 'board_deleted'],
  tools: ['tool_added', 'tool_deleted'],
};

function ActionBadge({ action }: { action: string }) {
  const badge = ACTION_BADGE[action] ?? { label: action, cls: 'bg-gray-100 text-gray-600' };
  return (
    <span className={`px-2 py-0.5 text-xs rounded-full font-medium ${badge.cls}`}>
      {badge.label}
    </span>
  );
}

function formatTime(ts: string): string {
  return new Date(ts).toLocaleString();
}

function filterByGroup(entries: ActivityEntry[], group: ActionGroup): ActivityEntry[] {
  if (group === 'all') return entries;
  return entries.filter((e) => GROUP_ACTIONS[group].includes(e.action));
}

export default function HistoryPage() {
  const [usernameFilter, setUsernameFilter] = useState('');
  const [actionGroup, setActionGroup] = useState<ActionGroup>('all');

  const { data: entries = [], isLoading } = useQuery({
    queryKey: ['activity'],
    queryFn: () => listActivity({ limit: 200 }),
  });

  const filtered = filterByGroup(entries, actionGroup).filter((e) =>
    usernameFilter ? e.username.toLowerCase().includes(usernameFilter.toLowerCase()) : true,
  );

  const groups: { label: string; value: ActionGroup }[] = [
    { label: 'All', value: 'all' },
    { label: 'Bookings', value: 'bookings' },
    { label: 'Device changes', value: 'board_changes' },
    { label: 'Tools', value: 'tools' },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-5xl mx-auto px-4 py-6">
        <Link
          to="/boards"
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 mb-4"
        >
          <ArrowLeft size={14} /> Back to inventory
        </Link>
        <h1 className="text-2xl font-bold text-gray-900 mb-4">Activity Log</h1>

        {/* Filters */}
        <div className="flex gap-2 mb-4 flex-wrap items-center">
          <input
            className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Filter by user…"
            value={usernameFilter}
            onChange={(e) => setUsernameFilter(e.target.value)}
          />
          {groups.map(({ label, value }) => (
            <button
              key={value}
              onClick={() => setActionGroup(value)}
              className={`px-3 py-1.5 text-sm rounded-lg ${
                actionGroup === value
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
        ) : filtered.length === 0 ? (
          <div className="text-center text-gray-400 py-20">No activity found</div>
        ) : (
          <div className="bg-white rounded-xl border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  {['Time', 'Action', 'Device', 'User', 'Detail'].map((h) => (
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
                {filtered.map((entry) => (
                  <tr key={entry.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                      {formatTime(entry.timestamp)}
                    </td>
                    <td className="px-4 py-3">
                      <ActionBadge action={entry.action} />
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-800">
                      {entry.board_id ? (
                        <Link
                          to={`/boards/${entry.board_id}`}
                          className="hover:underline"
                        >
                          {entry.board_name || entry.board_id}
                        </Link>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-600">{entry.username || '—'}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{entry.detail || '—'}</td>
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
