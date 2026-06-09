import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Layers, Plus, Trash2, X } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  bookSetup,
  createSetup,
  deleteSetup,
  getDefaultUser,
  listBoards,
  listSetups,
  releaseSetupBooking,
  setDefaultUser,
} from '../api/client';
import type { SetupInfo } from '../api/types';

// ── helpers ───────────────────────────────────────────────────────────────────

function formatTime(ts: string) {
  return new Date(ts).toLocaleString();
}

function SetupStatusBadge({ setup, me }: { setup: SetupInfo; me: string }) {
  if (setup.active_booking) {
    const mine = setup.active_booking.username === me;
    return (
      <span className={`px-2 py-0.5 text-xs rounded-full font-medium ${mine ? 'bg-blue-100 text-blue-700' : 'bg-amber-100 text-amber-700'}`}>
        {mine ? 'Booked by you' : `Booked by ${setup.active_booking.username}`}
      </span>
    );
  }
  if (setup.all_available) {
    return <span className="px-2 py-0.5 text-xs rounded-full font-medium bg-green-100 text-green-700">All available</span>;
  }
  return <span className="px-2 py-0.5 text-xs rounded-full font-medium bg-amber-100 text-amber-700">Partially unavailable</span>;
}

function DeviceRow({ board }: { board: SetupInfo['boards'][0] }) {
  const blocked = !!board.active_booking_username;
  return (
    <div className="flex items-center gap-2 text-xs py-1">
      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${blocked ? 'bg-red-400' : board.agent_online ? 'bg-green-400' : 'bg-gray-300'}`} />
      {board.device_id && (
        <span className="font-mono bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded border">{board.device_id}</span>
      )}
      <span className="font-medium text-gray-800">{board.board_name}</span>
      {board.location && <span className="text-gray-400">{board.location}</span>}
      {blocked && (
        <span className="text-red-500 ml-auto">
          booked by {board.active_booking_username}
          {board.active_booking_setup_name && ` (${board.active_booking_setup_name})`}
        </span>
      )}
      {!blocked && !board.agent_online && <span className="text-gray-400 ml-auto">offline</span>}
    </div>
  );
}

// ── Add Setup Modal ───────────────────────────────────────────────────────────

function AddSetupModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [username, setUsername] = useState(getDefaultUser());
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState('');

  const { data: boards = [] } = useQuery({ queryKey: ['boards'], queryFn: listBoards });

  const mut = useMutation({
    mutationFn: () =>
      createSetup({ name, description, board_ids: Array.from(selectedIds) }, username),
    onSuccess: () => {
      setDefaultUser(username);
      qc.invalidateQueries({ queryKey: ['setups'] });
      onClose();
    },
  });

  function toggle(id: string) {
    setSelectedIds((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }

  const q = search.toLowerCase();
  const filtered = boards.filter(
    (b) =>
      !selectedIds.has(b.id) && (
        !q ||
        b.name.toLowerCase().includes(q) ||
        b.device_id.toLowerCase().includes(q) ||
        b.location.toLowerCase().includes(q)
      ),
  );
  const selected = boards.filter((b) => selectedIds.has(b.id));

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-gray-900">Add Setup</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-gray-600">Your username <span className="text-red-500">*</span></span>
            <input className="border rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Required" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-gray-600">Name <span className="text-red-500">*</span></span>
            <input className="border rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. FPGA Test Bench" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-gray-600">Description</span>
            <textarea className="border rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500" rows={2}
              value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>

          <div className="flex flex-col gap-2">
            <span className="text-xs font-medium text-gray-600">Devices</span>

            {/* Selected chips */}
            {selected.length > 0 && (
              <div className="flex flex-wrap gap-1.5 p-2 bg-blue-50 rounded-lg border border-blue-100">
                {selected.map((b) => (
                  <button
                    key={b.id}
                    type="button"
                    onClick={() => toggle(b.id)}
                    className="flex items-center gap-1 px-2 py-0.5 bg-white border border-blue-200 rounded-full text-xs text-blue-700 hover:bg-red-50 hover:border-red-200 hover:text-red-600 group"
                  >
                    {b.device_id && <span className="font-mono">{b.device_id}</span>}
                    <span>{b.name}</span>
                    <X size={10} className="opacity-50 group-hover:opacity-100" />
                  </button>
                ))}
              </div>
            )}

            {/* Search */}
            <div className="flex items-center gap-2 border rounded-lg px-3 py-1.5 bg-white focus-within:ring-2 focus-within:ring-blue-500">
              <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z" />
              </svg>
              <input
                className="text-sm flex-1 focus:outline-none bg-transparent"
                placeholder="Search by name, ID, location…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {search && (
                <button onClick={() => setSearch('')} className="text-gray-400 hover:text-gray-600">
                  <X size={12} />
                </button>
              )}
            </div>

            {/* Filtered list */}
            <div className="border rounded-lg divide-y max-h-52 overflow-y-auto">
              {boards.length === 0 && (
                <p className="text-xs text-gray-400 px-3 py-2">No devices in inventory</p>
              )}
              {boards.length > 0 && filtered.length === 0 && (
                <p className="text-xs text-gray-400 px-3 py-2">
                  {search ? 'No devices match your search' : 'All devices already selected'}
                </p>
              )}
              {filtered.map((b) => (
                <label key={b.id} className="flex items-center gap-3 px-3 py-2 hover:bg-gray-50 cursor-pointer">
                  <input type="checkbox" className="accent-blue-600"
                    checked={false} onChange={() => toggle(b.id)} />
                  <div className="flex items-center gap-2 min-w-0">
                    {b.device_id && (
                      <span className="font-mono text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded border flex-shrink-0">{b.device_id}</span>
                    )}
                    <span className="text-sm font-medium text-gray-800 truncate">{b.name}</span>
                    {b.location && <span className="text-xs text-gray-400 truncate">{b.location}</span>}
                  </div>
                </label>
              ))}
            </div>

            <p className="text-xs text-gray-400">
              {selectedIds.size > 0
                ? `${selectedIds.size} device${selectedIds.size !== 1 ? 's' : ''} selected`
                : 'No devices selected'}
            </p>
          </div>

          {mut.error && <p className="text-xs text-red-600">{(mut.error as Error).message}</p>}

          <div className="flex gap-2 justify-end mt-2">
            <button onClick={onClose} className="px-4 py-1.5 border rounded-lg text-sm hover:bg-gray-50">Cancel</button>
            <button
              onClick={() => mut.mutate()}
              disabled={mut.isPending || !name || !username || selectedIds.size === 0}
              className="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {mut.isPending ? 'Creating…' : 'Create'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Book Setup Modal ──────────────────────────────────────────────────────────

function BookSetupModal({ setup, onClose }: { setup: SetupInfo; onClose: () => void }) {
  const qc = useQueryClient();
  const [username, setUsername] = useState(getDefaultUser());
  const [hours, setHours] = useState(4);
  const [comment, setComment] = useState('');

  const mut = useMutation({
    mutationFn: () => bookSetup(setup.id, hours, comment, username),
    onSuccess: () => {
      setDefaultUser(username);
      qc.invalidateQueries({ queryKey: ['setups'] });
      qc.invalidateQueries({ queryKey: ['boards'] });
      onClose();
    },
  });

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Book Setup</h2>
            <p className="text-sm text-gray-500">{setup.name}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-gray-600">Your username <span className="text-red-500">*</span></span>
            <input className="border rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Required" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-gray-600">Duration (hours)</span>
            <input type="number" min={1} className="border rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={hours} onChange={(e) => setHours(Math.max(1, Number(e.target.value)))} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-gray-600">Comment <span className="text-gray-400 font-normal">(optional)</span></span>
            <textarea rows={2} className="border rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>

          <div className="rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600">
            This will book all {setup.boards.length} device{setup.boards.length !== 1 ? 's' : ''} atomically.
            If any device is unavailable the entire booking will fail.
          </div>

          {mut.error && <p className="text-xs text-red-600">{(mut.error as Error).message}</p>}

          <div className="flex gap-2 justify-end mt-2">
            <button onClick={onClose} className="px-4 py-1.5 border rounded-lg text-sm hover:bg-gray-50">Cancel</button>
            <button
              onClick={() => mut.mutate()}
              disabled={mut.isPending || !username}
              className="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {mut.isPending ? 'Booking…' : `Book for ${hours}h`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Setup Card ────────────────────────────────────────────────────────────────

function SetupCard({ setup }: { setup: SetupInfo }) {
  const qc = useQueryClient();
  const me = getDefaultUser();
  const [showBook, setShowBook] = useState(false);

  const myBooking = setup.active_booking?.username === me;

  const releaseMut = useMutation({
    mutationFn: () => releaseSetupBooking(setup.id, me),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['setups'] });
      qc.invalidateQueries({ queryKey: ['boards'] });
    },
  });

  const deleteMut = useMutation({
    mutationFn: () => deleteSetup(setup.id, me),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['setups'] }),
  });

  return (
    <div className="bg-white rounded-xl border p-5">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-start gap-2 flex-wrap">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="font-semibold text-gray-900">{setup.name}</h2>
              <SetupStatusBadge setup={setup} me={me} />
            </div>
            {setup.description && (
              <p className="text-xs text-gray-500 mt-0.5">{setup.description}</p>
            )}
          </div>
        </div>
        <button
          onClick={() => { if (confirm(`Delete setup "${setup.name}"?`)) deleteMut.mutate(); }}
          disabled={deleteMut.isPending}
          className="text-red-300 hover:text-red-600 disabled:opacity-40 flex-shrink-0"
          title="Delete setup"
        >
          <Trash2 size={15} />
        </button>
      </div>

      {/* Device list */}
      <div className="border rounded-lg px-3 py-1 mb-3 divide-y divide-gray-50">
        {setup.boards.length === 0 ? (
          <p className="text-xs text-gray-400 py-2">No devices</p>
        ) : (
          setup.boards.map((b) => <DeviceRow key={b.board_id} board={b} />)
        )}
      </div>

      {/* Active booking info */}
      {setup.active_booking && (
        <div className="text-xs text-gray-500 mb-3">
          Booked until {formatTime(setup.active_booking.end_time)}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 flex-wrap">
        {myBooking && (
          <button
            onClick={() => releaseMut.mutate()}
            disabled={releaseMut.isPending}
            className="px-3 py-1.5 text-xs border border-amber-300 text-amber-700 rounded-lg hover:bg-amber-50 disabled:opacity-50"
          >
            {releaseMut.isPending ? 'Releasing…' : 'Release'}
          </button>
        )}
        {!setup.active_booking && (
          <>
            <button
              onClick={() => setShowBook(true)}
              className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Book Setup
            </button>
            {!setup.all_available && (
              <span className="text-xs text-amber-600">Some devices unavailable</span>
            )}
          </>
        )}
        {deleteMut.error && (
          <span className="text-xs text-red-600">{(deleteMut.error as Error).message}</span>
        )}
      </div>

      {showBook && <BookSetupModal setup={setup} onClose={() => setShowBook(false)} />}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function SetupsPage() {
  const [showAdd, setShowAdd] = useState(false);

  const { data: setups = [], isLoading } = useQuery({
    queryKey: ['setups'],
    queryFn: listSetups,
    refetchInterval: 15_000,
  });

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto px-4 py-6">
        <Link to="/boards"
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 mb-4">
          <ArrowLeft size={14} /> Back to inventory
        </Link>

        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Layers size={22} /> Setups
            </h1>
            <p className="text-sm text-gray-500">{setups.length} setup{setups.length !== 1 ? 's' : ''}</p>
          </div>
          <button
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
          >
            <Plus size={14} /> Add Setup
          </button>
        </div>

        {isLoading ? (
          <div className="text-center text-gray-400 py-20">Loading…</div>
        ) : setups.length === 0 ? (
          <div className="text-center py-20">
            <Layers size={32} className="mx-auto text-gray-300 mb-3" />
            <p className="text-gray-400">No setups yet</p>
            <button onClick={() => setShowAdd(true)}
              className="mt-4 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700">
              Create your first setup
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {setups.map((s) => <SetupCard key={s.id} setup={s} />)}
          </div>
        )}
      </div>

      {showAdd && <AddSetupModal onClose={() => setShowAdd(false)} />}
    </div>
  );
}
