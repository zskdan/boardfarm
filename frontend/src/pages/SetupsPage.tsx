import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, LayoutGrid, Layers, List, Pencil, Plus, Table2, Trash2, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  bookSetup,
  createSetup,
  deleteSetup,
  getDefaultUser,
  listDevices,
  listSetups,
  releaseSetupBooking,
  setDefaultUser,
  updateSetup,
} from '../api/client';
import type { SetupInfo } from '../api/types';
import { VersionBadge } from '../components/VersionBadge';

// ── helpers ───────────────────────────────────────────────────────────────────

type ViewMode = 'list' | 'table' | 'grid';
type SortKey = 'name' | 'status' | 'devices';
type SortDir = 'asc' | 'desc';

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

function DeviceRow({ device }: { device: SetupInfo['devices'][0] }) {
  const blocked = !!device.active_booking_username;
  return (
    <Link
      to={`/devices/${device.id}`}
      className="flex items-center gap-2 text-xs py-1 px-1 -mx-1 rounded hover:bg-gray-50 group"
    >
      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${blocked ? 'bg-blue-400' : device.agent_online ? 'bg-green-400' : 'bg-gray-300'}`} />
      {device.device_id && (
        <span className="font-mono bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded border">{device.device_id}</span>
      )}
      <span className="font-medium text-gray-800 group-hover:text-blue-600 group-hover:underline">{device.name}</span>
      {device.location && <span className="text-gray-400">{device.location}</span>}
      <VersionBadge deployedVersion={device.deployed_version} versionScript={device.version_script} />
      {blocked && (
        <span className="text-blue-500 ml-auto">
          booked by {device.active_booking_username}
          {device.active_booking_setup_name && ` (${device.active_booking_setup_name})`}
        </span>
      )}
      {!blocked && !device.agent_online && <span className="text-gray-400 ml-auto">offline</span>}
    </Link>
  );
}

function DeviceChip({ device }: { device: SetupInfo['devices'][0] }) {
  const blocked = !!device.active_booking_username;
  const dotColor = blocked ? 'bg-blue-400' : device.agent_online ? 'bg-green-400' : 'bg-gray-300';
  return (
    <Link
      to={`/devices/${device.id}`}
      title={blocked ? `Booked by ${device.active_booking_username}` : device.name}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border bg-white text-xs text-gray-700 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 max-w-[140px]"
    >
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dotColor}`} />
      <span className="truncate">{device.name}</span>
    </Link>
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

  const { data: devices = [] } = useQuery({ queryKey: ['devices'], queryFn: listDevices });

  const mut = useMutation({
    mutationFn: () =>
      createSetup({ name, description, device_ids: Array.from(selectedIds) }, username),
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
  const filtered = devices.filter(
    (b) =>
      !selectedIds.has(b.id) && (
        !q ||
        b.name.toLowerCase().includes(q) ||
        b.device_id.toLowerCase().includes(q) ||
        b.location.toLowerCase().includes(q)
      ),
  );
  const selected = devices.filter((b) => selectedIds.has(b.id));

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
              {devices.length === 0 && (
                <p className="text-xs text-gray-400 px-3 py-2">No devices in inventory</p>
              )}
              {devices.length > 0 && filtered.length === 0 && (
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

// ── Edit Setup Modal ──────────────────────────────────────────────────────────

function EditSetupModal({ setup, onClose }: { setup: SetupInfo; onClose: () => void }) {
  const qc = useQueryClient();
  const me = getDefaultUser();
  const [name, setName] = useState(setup.name);
  const [description, setDescription] = useState(setup.description ?? '');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    new Set(setup.devices.map((d) => d.id)),
  );
  const [search, setSearch] = useState('');

  const { data: allDevices = [] } = useQuery({ queryKey: ['devices'], queryFn: listDevices });

  const mut = useMutation({
    mutationFn: () =>
      updateSetup(setup.id, { name, description, device_ids: Array.from(selectedIds) }, me),
    onSuccess: () => {
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
  const selected = allDevices.filter((d) => selectedIds.has(d.id));
  const available = allDevices.filter(
    (d) =>
      !selectedIds.has(d.id) &&
      (!q ||
        d.name.toLowerCase().includes(q) ||
        d.device_id.toLowerCase().includes(q) ||
        d.location.toLowerCase().includes(q)),
  );

  const dirty =
    name !== setup.name ||
    description !== (setup.description ?? '') ||
    selectedIds.size !== setup.devices.length ||
    setup.devices.some((d) => !selectedIds.has(d.id));

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-gray-900">Edit Setup</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-gray-600">Name <span className="text-red-500">*</span></span>
            <input className="border rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={name} onChange={(e) => setName(e.target.value)} />
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
                {selected.map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => toggle(d.id)}
                    className="flex items-center gap-1 px-2 py-0.5 bg-white border border-blue-200 rounded-full text-xs text-blue-700 hover:bg-red-50 hover:border-red-200 hover:text-red-600 group"
                  >
                    {d.device_id && <span className="font-mono">{d.device_id}</span>}
                    <span>{d.name}</span>
                    <X size={10} className="opacity-50 group-hover:opacity-100" />
                  </button>
                ))}
              </div>
            )}
            {selected.length === 0 && (
              <p className="text-xs text-amber-600 px-1">No devices selected — setup will be empty</p>
            )}

            {/* Search */}
            <div className="flex items-center gap-2 border rounded-lg px-3 py-1.5 bg-white focus-within:ring-2 focus-within:ring-blue-500">
              <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z" />
              </svg>
              <input
                className="text-sm flex-1 focus:outline-none bg-transparent"
                placeholder="Search to add devices…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {search && (
                <button onClick={() => setSearch('')} className="text-gray-400 hover:text-gray-600">
                  <X size={12} />
                </button>
              )}
            </div>

            {/* Available list */}
            <div className="border rounded-lg divide-y max-h-48 overflow-y-auto">
              {allDevices.length === 0 && (
                <p className="text-xs text-gray-400 px-3 py-2">No devices in inventory</p>
              )}
              {allDevices.length > 0 && available.length === 0 && (
                <p className="text-xs text-gray-400 px-3 py-2">
                  {search ? 'No devices match your search' : 'All devices already selected'}
                </p>
              )}
              {available.map((d) => (
                <label key={d.id} className="flex items-center gap-3 px-3 py-2 hover:bg-gray-50 cursor-pointer">
                  <input type="checkbox" className="accent-blue-600"
                    checked={false} onChange={() => toggle(d.id)} />
                  <div className="flex items-center gap-2 min-w-0">
                    {d.device_id && (
                      <span className="font-mono text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded border flex-shrink-0">{d.device_id}</span>
                    )}
                    <span className="text-sm font-medium text-gray-800 truncate">{d.name}</span>
                    {d.location && <span className="text-xs text-gray-400 truncate">{d.location}</span>}
                  </div>
                </label>
              ))}
            </div>
          </div>

          {mut.error && <p className="text-xs text-red-600">{(mut.error as Error).message}</p>}

          <div className="flex gap-2 justify-end mt-2">
            <button onClick={onClose} className="px-4 py-1.5 border rounded-lg text-sm hover:bg-gray-50">Cancel</button>
            <button
              onClick={() => mut.mutate()}
              disabled={mut.isPending || !name || !dirty}
              className="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {mut.isPending ? 'Saving…' : 'Save'}
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
      qc.invalidateQueries({ queryKey: ['devices'] });
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
            This will book all {setup.devices.length} device{setup.devices.length !== 1 ? 's' : ''} atomically.
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

// ── Shared row/card action logic ────────────────────────────────────────────

function useSetupActions(setup: SetupInfo) {
  const qc = useQueryClient();
  const me = getDefaultUser();
  const myBooking = setup.active_booking?.username === me;

  const releaseMut = useMutation({
    mutationFn: () => releaseSetupBooking(setup.id, me),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['setups'] });
      qc.invalidateQueries({ queryKey: ['devices'] });
    },
  });

  const deleteMut = useMutation({
    mutationFn: () => deleteSetup(setup.id, me),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['setups'] }),
  });

  return { me, myBooking, releaseMut, deleteMut };
}

// ── Setup Card ────────────────────────────────────────────────────────────────

function SetupCard({ setup }: { setup: SetupInfo }) {
  const [showBook, setShowBook] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const { me, myBooking, releaseMut, deleteMut } = useSetupActions(setup);

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
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={() => setShowEdit(true)}
            className="text-gray-400 hover:text-blue-600"
            title="Edit setup"
          >
            <Pencil size={15} />
          </button>
          <button
            onClick={() => { if (confirm(`Delete setup "${setup.name}"?`)) deleteMut.mutate(); }}
            disabled={deleteMut.isPending}
            className="text-red-300 hover:text-red-600 disabled:opacity-40"
            title="Delete setup"
          >
            <Trash2 size={15} />
          </button>
        </div>
      </div>

      {/* Device list */}
      <div className="border rounded-lg px-3 py-1 mb-3 divide-y divide-gray-50">
        {setup.devices.length === 0 ? (
          <p className="text-xs text-gray-400 py-2">No devices</p>
        ) : (
          setup.devices.map((b) => <DeviceRow key={b.id} device={b} />)
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
      {showEdit && <EditSetupModal setup={setup} onClose={() => setShowEdit(false)} />}
    </div>
  );
}

// ── Setup actions (Table row / Grid card) ───────────────────────────────────

function SetupActions({ setup }: { setup: SetupInfo }) {
  const [showBook, setShowBook] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const { myBooking, releaseMut, deleteMut } = useSetupActions(setup);

  return (
    <div className="flex items-center gap-2 flex-wrap justify-end">
      {myBooking && (
        <button
          onClick={() => releaseMut.mutate()}
          disabled={releaseMut.isPending}
          className="px-2.5 py-1 text-xs border border-amber-300 text-amber-700 rounded-lg hover:bg-amber-50 disabled:opacity-50"
        >
          {releaseMut.isPending ? 'Releasing…' : 'Release'}
        </button>
      )}
      {!setup.active_booking && (
        <button
          onClick={() => setShowBook(true)}
          className="px-2.5 py-1 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          Book
        </button>
      )}
      <button
        onClick={() => setShowEdit(true)}
        className="text-gray-400 hover:text-blue-600"
        title="Edit setup"
      >
        <Pencil size={15} />
      </button>
      <button
        onClick={() => { if (confirm(`Delete setup "${setup.name}"?`)) deleteMut.mutate(); }}
        disabled={deleteMut.isPending}
        className="text-red-300 hover:text-red-600 disabled:opacity-40"
        title="Delete setup"
      >
        <Trash2 size={15} />
      </button>
      {deleteMut.error && (
        <span className="text-xs text-red-600 w-full text-right">{(deleteMut.error as Error).message}</span>
      )}

      {showBook && <BookSetupModal setup={setup} onClose={() => setShowBook(false)} />}
      {showEdit && <EditSetupModal setup={setup} onClose={() => setShowEdit(false)} />}
    </div>
  );
}

// ── Table view ───────────────────────────────────────────────────────────────

function SortableTh({
  label, sortKeyFor, sortKey, sortDir, onSort,
}: {
  label: string; sortKeyFor: SortKey; sortKey: SortKey; sortDir: SortDir; onSort: (k: SortKey) => void;
}) {
  const active = sortKey === sortKeyFor;
  return (
    <th
      onClick={() => onSort(sortKeyFor)}
      className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide cursor-pointer select-none hover:text-gray-700"
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <span className={active ? 'text-gray-700' : 'text-gray-300'}>
          {active ? (sortDir === 'asc' ? '▲' : '▼') : '⇅'}
        </span>
      </span>
    </th>
  );
}

function SetupTableView({
  setups, me, sortKey, sortDir, onSort,
}: {
  setups: SetupInfo[]; me: string; sortKey: SortKey; sortDir: SortDir; onSort: (k: SortKey) => void;
}) {
  return (
    <div className="bg-white rounded-xl border overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 border-b">
          <tr>
            <SortableTh label="Setup" sortKeyFor="name" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
            <SortableTh label="Status" sortKeyFor="status" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
            <SortableTh label="Devices" sortKeyFor="devices" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wide">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {setups.map((setup) => (
            <tr key={setup.id} className="hover:bg-gray-50">
              <td className="px-4 py-3 align-top">
                <div className="max-w-[240px] truncate font-medium text-gray-900" title={setup.name}>{setup.name}</div>
                {setup.description && (
                  <div className="max-w-[240px] truncate text-xs text-gray-400 mt-0.5" title={setup.description}>{setup.description}</div>
                )}
              </td>
              <td className="px-4 py-3 align-top"><SetupStatusBadge setup={setup} me={me} /></td>
              <td className="px-4 py-3 align-top">
                {setup.devices.length === 0 ? (
                  <span className="text-gray-300">—</span>
                ) : (
                  <div className="flex flex-wrap gap-1 max-w-md">
                    {setup.devices.map((d) => <DeviceChip key={d.id} device={d} />)}
                  </div>
                )}
              </td>
              <td className="px-4 py-3 align-top"><SetupActions setup={setup} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Grid view ────────────────────────────────────────────────────────────────

function SetupGridView({ setups, me }: { setups: SetupInfo[]; me: string }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {setups.map((setup) => (
        <div key={setup.id} className="bg-white rounded-xl border p-4 flex flex-col gap-2">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="font-semibold text-gray-900 truncate" title={setup.name}>{setup.name}</h2>
              <SetupStatusBadge setup={setup} me={me} />
            </div>
            {setup.description && (
              <p className="text-xs text-gray-500 mt-0.5 truncate" title={setup.description}>{setup.description}</p>
            )}
          </div>
          {setup.devices.length === 0 ? (
            <span className="text-xs text-gray-300">No devices</span>
          ) : (
            <div className="flex flex-wrap gap-1">
              {setup.devices.map((d) => <DeviceChip key={d.id} device={d} />)}
            </div>
          )}
          <SetupActions setup={setup} />
        </div>
      ))}
    </div>
  );
}

// ── View toggle ──────────────────────────────────────────────────────────────

function ViewToggle({ value, onChange }: { value: ViewMode; onChange: (v: ViewMode) => void }) {
  const options: { key: ViewMode; label: string; icon: typeof List }[] = [
    { key: 'list', label: 'List', icon: List },
    { key: 'table', label: 'Table', icon: Table2 },
    { key: 'grid', label: 'Grid', icon: LayoutGrid },
  ];
  return (
    <div className="inline-flex items-center border rounded-lg bg-white overflow-hidden">
      {options.map(({ key, label, icon: Icon }, i) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          title={label}
          className={`flex items-center gap-1.5 px-3 py-2 text-sm ${i > 0 ? 'border-l' : ''} ${
            value === key ? 'bg-blue-50 text-blue-700' : 'text-gray-500 hover:bg-gray-50'
          }`}
        >
          <Icon size={14} /> {label}
        </button>
      ))}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

function statusRank(setup: SetupInfo, me: string) {
  // Ascending order: All available(0) → Partial(1) → Booked by you(2) → Booked by other(3)
  if (setup.active_booking) return setup.active_booking.username === me ? 2 : 3;
  return setup.all_available ? 0 : 1;
}

export default function SetupsPage() {
  const [showAdd, setShowAdd] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const { data: setups = [], isLoading } = useQuery({
    queryKey: ['setups'],
    queryFn: listSetups,
    refetchInterval: 15_000,
  });

  const me = getDefaultUser();

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  }

  const sortedSetups = useMemo(() => {
    const dir = sortDir === 'asc' ? 1 : -1;
    return [...setups].sort((a, b) => {
      switch (sortKey) {
        case 'name': return a.name.localeCompare(b.name) * dir;
        case 'status': return (statusRank(a, me) - statusRank(b, me)) * dir;
        case 'devices': return (a.devices.length - b.devices.length) * dir;
        default: return 0;
      }
    });
  }, [setups, sortKey, sortDir, me]);

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-6">
        <Link to="/devices"
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 mb-4">
          <ArrowLeft size={14} /> Back to inventory
        </Link>

        <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Layers size={22} /> Setups
            </h1>
            <p className="text-sm text-gray-500">{setups.length} setup{setups.length !== 1 ? 's' : ''}</p>
          </div>
          <div className="flex items-center gap-2">
            <ViewToggle value={viewMode} onChange={setViewMode} />
            <button
              onClick={() => setShowAdd(true)}
              className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
            >
              <Plus size={14} /> Add Setup
            </button>
          </div>
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
        ) : viewMode === 'table' ? (
          <SetupTableView setups={sortedSetups} me={me} sortKey={sortKey} sortDir={sortDir} onSort={handleSort} />
        ) : viewMode === 'grid' ? (
          <SetupGridView setups={setups} me={me} />
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
