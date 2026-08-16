import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Clock,
  Copy,
  History,
  Layers,
  MapPin,
  Pencil,
  Plus,
  RefreshCw,
  Settings,
  Trash2,
  Unlock,
  X,
} from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  bookDevice,
  deleteDevice,
  getBookingLimit,
  getDefaultUser,
  getServerUrl,
  getToken,
  listDevices,
  releaseBooking,
  setBookingLimit,
  setDefaultUser,
  setServerUrl,
  setToken,
  getLocalAppName,
  setLocalAppName,
} from '../api/client';
import type { BookingLimit } from '../api/client';
import type { DeviceInfo } from '../api/types';
import StatusBadge from '../components/StatusBadge';
import { VersionBadge } from '../components/VersionBadge';
import { AddDeviceModal, EditDeviceModal, Field, inputCls, ModalActions, ModalCard, Overlay } from '../components/EditDeviceModal';
import { useStatusSocket } from '../hooks/useStatusSocket';

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

const TAG_COLORS = [
  'bg-blue-100 text-blue-700',
  'bg-green-100 text-green-700',
  'bg-purple-100 text-purple-700',
  'bg-orange-100 text-orange-700',
  'bg-pink-100 text-pink-700',
  'bg-teal-100 text-teal-700',
  'bg-yellow-100 text-yellow-700',
  'bg-indigo-100 text-indigo-700',
  'bg-cyan-100 text-cyan-700',
  'bg-rose-100 text-rose-700',
];

function tagColor(key: string): string {
  let hash = 0;
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  return TAG_COLORS[hash % TAG_COLORS.length];
}

function formatTag(k: string, v: unknown): string {
  if (v === true || v === 'true') return k;
  if (v === false || v === 'false') return `${k}: false`;
  const s = String(v);
  if (/^-?\d+(\.\d+)?$/.test(s)) return `${k}: ${s}`;
  return s; // plain string value — show value only
}

function limitLabel(l: BookingLimit): string {
  if (l === 'unlimited') return 'Unlimited';
  if (l === 'never') return 'No expiry';
  return `Max ${l}h`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Booking Limit Modal
// ─────────────────────────────────────────────────────────────────────────────

function BookingLimitModal({ onClose }: { onClose: () => void }) {
  const cur = getBookingLimit();
  const [kind, setKind] = useState<'hours' | 'unlimited' | 'never'>(
    cur === 'unlimited' ? 'unlimited' : cur === 'never' ? 'never' : 'hours',
  );
  const [hours, setHours] = useState(typeof cur === 'number' ? cur : 24);

  function save() {
    setBookingLimit(kind === 'hours' ? Math.max(1, hours) : kind);
    onClose();
  }

  return (
    <Overlay onClose={onClose}>
      <ModalCard title="Booking limit" onClose={onClose}>
        <div className="flex flex-col gap-3">
          <p className="text-xs text-gray-500">Maximum duration a device can be reserved at once.</p>
          <Field label="Mode">
            <select className={inputCls} value={kind}
              onChange={(e) => setKind(e.target.value as typeof kind)}>
              <option value="hours">Limited (hours)</option>
              <option value="unlimited">Unlimited</option>
              <option value="never">Never expires</option>
            </select>
          </Field>
          {kind === 'hours' && (
            <Field label="Max hours">
              <input type="number" min={1} className={inputCls} value={hours}
                onChange={(e) => setHours(Math.max(1, Number(e.target.value)))} />
            </Field>
          )}
          <p className="text-xs text-gray-400">
            {kind === 'hours' && `Bookings expire after ${hours}h unless manually released`}
            {kind === 'unlimited' && 'Users can choose any duration'}
            {kind === 'never' && 'Bookings never auto-expire — manual release only'}
          </p>
          <ModalActions onCancel={onClose} onConfirm={save} confirmLabel="Save" />
        </div>
      </ModalCard>
    </Overlay>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Settings Modal  (server URL · default user · token)
// ─────────────────────────────────────────────────────────────────────────────

function SettingsModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [url, setUrl] = useState(getServerUrl());
  const [defaultUser, setDefaultUserState] = useState(getDefaultUser());
  const [token, setTokenState] = useState(getToken());
  const [appName, setAppNameState] = useState(getLocalAppName());

  function save() {
    setServerUrl(url);
    setDefaultUser(defaultUser);
    setToken(token);
    setLocalAppName(appName);
    qc.invalidateQueries({ queryKey: ['serverInfo'] });
    onClose();
  }
  function disconnect() {
    setServerUrl(''); setDefaultUser(''); setToken('');
    navigate('/');
  }

  return (
    <Overlay onClose={onClose}>
      <ModalCard title="Settings" onClose={onClose}>
        <div className="flex flex-col gap-3">
          <Field label="Server URL">
            <input className={inputCls} value={url} onChange={(e) => setUrl(e.target.value)} />
          </Field>
          <Field label="Default username">
            <input className={inputCls} value={defaultUser}
              onChange={(e) => setDefaultUserState(e.target.value)}
              placeholder="Pre-filled in all action forms" />
          </Field>
          <Field label="Token">
            <input type="password" className={inputCls} value={token}
              onChange={(e) => setTokenState(e.target.value)} />
          </Field>
          <Field label="App name override">
            <input className={inputCls} value={appName}
              onChange={(e) => setAppNameState(e.target.value)}
              placeholder="Leave blank to use server default" />
          </Field>
          <ModalActions onCancel={onClose} onConfirm={save} confirmLabel="Save" />
          <button onClick={disconnect} className="text-xs text-red-500 hover:underline text-center mt-1">
            Disconnect (return to setup)
          </button>
        </div>
      </ModalCard>
    </Overlay>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Book Modal
// ─────────────────────────────────────────────────────────────────────────────

function BookModal({ device, onClose }: { device: DeviceInfo; onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const limit = getBookingLimit();
  const isNever = limit === 'never';
  const maxHours = typeof limit === 'number' ? limit : undefined;
  const [username, setUsernameState] = useState(getDefaultUser());
  const [hours, setHours] = useState(maxHours ? Math.min(4, maxHours) : 4);
  const [comment, setComment] = useState('');

  const mut = useMutation({
    mutationFn: () => bookDevice(device.id, isNever ? 1 : hours, comment, username),
    onSuccess: () => {
      setDefaultUser(username);
      qc.invalidateQueries({ queryKey: ['devices'] });
      onClose();
      navigate(`/devices/${device.id}`);
    },
  });

  return (
    <Overlay onClose={onClose}>
      <ModalCard title="Book device" subtitle={device.name} onClose={onClose}>
        <div className="flex flex-col gap-4">
          <Field label="Your username">
            <input className={inputCls} value={username}
              onChange={(e) => setUsernameState(e.target.value)}
              placeholder="Required" />
          </Field>
          {isNever ? (
            <div className="rounded-lg bg-blue-50 px-4 py-3 text-sm text-blue-800">
              This booking will not expire automatically — release it when you're done.
            </div>
          ) : (
            <Field label="Duration (hours)">
              <input type="number" min={1} {...(maxHours ? { max: maxHours } : {})}
                className={inputCls} value={hours}
                onChange={(e) => {
                  const v = Math.max(1, Number(e.target.value));
                  setHours(maxHours ? Math.min(maxHours, v) : v);
                }} />
              <span className="text-xs text-gray-400 mt-1">
                {maxHours ? `Maximum ${maxHours}h · extendable once` : 'No limit · extendable once'}
              </span>
            </Field>
          )}
          <Field label={<>Comment <span className="font-normal text-gray-400">(optional)</span></>}>
            <textarea rows={3} maxLength={500} className={`${inputCls} resize-none`}
              placeholder="What are you using this device for?"
              value={comment} onChange={(e) => setComment(e.target.value)} />
          </Field>
          {mut.error && <p className="text-xs text-red-600">{(mut.error as Error).message}</p>}
          <ModalActions onCancel={onClose} onConfirm={() => mut.mutate()}
            confirmLabel={mut.isPending ? 'Booking…' : isNever ? 'Book (permanent)' : `Book for ${hours}h`}
            confirmDisabled={mut.isPending || !username} />
        </div>
      </ModalCard>
    </Overlay>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Release Modal
// ─────────────────────────────────────────────────────────────────────────────

function ReleaseModal({ device, onClose }: { device: DeviceInfo; onClose: () => void }) {
  const qc = useQueryClient();
  const booking = device.active_booking!;
  const [username, setUsernameState] = useState(getDefaultUser());

  const mut = useMutation({
    mutationFn: () => releaseBooking(booking.id, username),
    onSuccess: () => {
      setDefaultUser(username);
      qc.invalidateQueries({ queryKey: ['devices'] });
      onClose();
    },
  });

  return (
    <Overlay onClose={onClose}>
      <ModalCard title={`Release — ${device.name}`} onClose={onClose}>
        <div className="flex flex-col gap-4">
          <div className="rounded-lg bg-amber-50 border border-amber-100 px-4 py-3">
            <p className="text-xs text-gray-400 mb-0.5">Currently booked by</p>
            <p className="font-semibold text-gray-900">{booking.username}</p>
            {booking.comment && (
              <p className="text-xs text-gray-400 mt-1 italic">{booking.comment}</p>
            )}
          </div>
          <Field label="Your username">
            <input className={inputCls} value={username}
              onChange={(e) => setUsernameState(e.target.value)}
              placeholder="Enter your username to confirm" />
          </Field>
          {mut.error && <p className="text-xs text-red-600">{(mut.error as Error).message}</p>}
          <ModalActions onCancel={onClose} onConfirm={() => mut.mutate()}
            confirmLabel={mut.isPending ? 'Releasing…' : 'Release device'}
            confirmDisabled={mut.isPending || !username} />
        </div>
      </ModalCard>
    </Overlay>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

type Modal = 'add' | 'settings' | 'limit' | null;

export default function InventoryPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState<Modal>(null);
  const [editDevice, setEditDevice] = useState<DeviceInfo | null>(null);
  const [cloneDevice, setCloneDevice] = useState<DeviceInfo | null>(null);
  const [bookDevice2, setBookDevice2] = useState<DeviceInfo | null>(null);
  const [releaseDevice, setReleaseDevice] = useState<DeviceInfo | null>(null);
  const [deleteMode, setDeleteMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const me = getDefaultUser();

  useStatusSocket();

  const { data: devices = [], isLoading, refetch, isFetching, isError } = useQuery({
    queryKey: ['devices'],
    queryFn: listDevices,
    refetchInterval: 15_000,
  });

  const deleteMut = useMutation({
    mutationFn: async (ids: string[]) => { for (const id of ids) await deleteDevice(id, me); },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['devices'] }); setSelected(new Set()); setDeleteMode(false); },
  });

  const filtered = devices.filter((d) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      d.name.toLowerCase().includes(q) ||
      d.device_id.toLowerCase().includes(q) ||
      d.location.toLowerCase().includes(q) ||
      d.description.toLowerCase().includes(q) ||
      (d.active_booking?.username ?? '').toLowerCase().includes(q) ||
      Object.keys(d.features).some(k => k.toLowerCase().includes(q))
    );
  });

  function toggleSelect(id: string) {
    setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }

  function confirmDelete() {
    if (selected.size === 0) return;
    if (!confirm(`Delete ${selected.size} device(s)? This cannot be undone.`)) return;
    deleteMut.mutate(Array.from(selected));
  }

  function cancelDelete() { setDeleteMode(false); setSelected(new Set()); }

  const isFree = (d: DeviceInfo) => d.enabled && !d.active_booking;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-6">

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between mb-6 gap-3 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Device Inventory</h1>
            <p className="text-sm text-gray-500">{devices.length} devices registered</p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Filter */}
            <div className="flex items-center gap-1.5 border rounded-lg bg-white px-3 py-1.5">
              <svg className="w-3.5 h-3.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z" />
              </svg>
              <input className="text-sm focus:outline-none w-36 bg-transparent" placeholder="Filter devices…"
                value={search} onChange={(e) => setSearch(e.target.value)} />
              {search && (
                <button onClick={() => setSearch('')} className="text-gray-400 hover:text-gray-600"><X size={13} /></button>
              )}
            </div>

            <button onClick={() => refetch()} className="p-2 rounded-lg border bg-white hover:bg-gray-50" title="Refresh">
              <RefreshCw size={15} className={isFetching ? 'animate-spin' : ''} />
            </button>

            {/* Booking limit */}
            <button onClick={() => setModal('limit')}
              className="flex items-center gap-1.5 px-3 py-2 border bg-white text-sm rounded-lg hover:bg-gray-50 text-gray-600">
              <Clock size={14} />
              {limitLabel(getBookingLimit())}
            </button>

            {/* Add Device */}
            <button onClick={() => setModal('add')}
              className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700">
              <Plus size={14} /> Add Device
            </button>

            {/* Settings */}
            <button onClick={() => setModal('settings')}
              className="flex items-center gap-1.5 px-3 py-2 border bg-white text-sm rounded-lg hover:bg-gray-50">
              <Settings size={14} /> Settings
            </button>

            {/* Delete mode */}
            {deleteMode ? (
              <>
                <button onClick={confirmDelete} disabled={selected.size === 0 || deleteMut.isPending}
                  className="flex items-center gap-1.5 px-3 py-2 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 disabled:opacity-40">
                  <Trash2 size={14} /> Delete {selected.size > 0 ? `(${selected.size})` : ''}
                </button>
                <button onClick={cancelDelete} className="flex items-center gap-1.5 px-3 py-2 border bg-white text-sm rounded-lg hover:bg-gray-50">
                  <X size={14} /> Cancel
                </button>
              </>
            ) : (
              <button onClick={() => setDeleteMode(true)}
                className="flex items-center gap-1.5 px-3 py-2 border bg-white text-sm rounded-lg hover:bg-gray-50 text-gray-600">
                <Trash2 size={14} /> Delete
              </button>
            )}

            {/* Setups */}
            <Link to="/setups"
              className="flex items-center gap-1.5 px-3 py-2 border bg-white text-sm rounded-lg hover:bg-gray-50 text-gray-600">
              <Layers size={14} /> Setups
            </Link>

            {/* History */}
            <Link to="/history"
              className="flex items-center gap-1.5 px-3 py-2 border bg-white text-sm rounded-lg hover:bg-gray-50 text-gray-600">
              <History size={14} /> History
            </Link>
          </div>
        </div>

        {isError && (
          <div className="mb-4 px-4 py-2 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
            Cannot reach server. Retrying…
          </div>
        )}

        {/* ── Table ──────────────────────────────────────────────────────── */}
        {isLoading ? (
          <div className="text-center text-gray-400 py-20">Loading…</div>
        ) : filtered.length === 0 ? (
          <div className="text-center text-gray-400 py-20">No devices found</div>
        ) : (
          <div className="bg-white rounded-xl border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  {deleteMode && <th className="w-10 px-4 py-3"></th>}
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Device</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Status</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Booked by</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Location</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Features</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Deployed</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wide">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map((d) => (
                  <tr key={d.id}
                    className={`transition-colors ${!d.enabled ? 'opacity-50' : ''} ${selected.has(d.id) ? 'bg-red-50' : 'hover:bg-gray-50'}`}
                  >
                    {deleteMode && (
                      <td className="px-4 py-3">
                        <input type="checkbox" checked={selected.has(d.id)}
                          onChange={() => toggleSelect(d.id)} className="w-4 h-4 accent-red-600" />
                      </td>
                    )}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {d.device_id && (
                          <span className="font-mono text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded border">
                            {d.device_id}
                          </span>
                        )}
                        <Link to={`/devices/${d.id}`} className="font-medium text-gray-900 hover:text-blue-600 hover:underline">
                          {d.name}
                        </Link>
                      </div>
                      {d.description && (
                        <p className="text-xs text-gray-400 mt-0.5 max-w-xs truncate">{d.description}</p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge agentOnline={d.agent_online} activeBooking={!!d.active_booking} enabled={d.enabled} hasAgent={!!d.host_ip} />
                    </td>
                    <td className="px-4 py-3">
                      {d.active_booking ? (
                        <div>
                          <span className="font-medium text-gray-800">{d.active_booking.username}</span>
                          {d.active_booking.comment && (
                            <p className="text-xs text-gray-400 mt-0.5 max-w-[160px] truncate" title={d.active_booking.comment}>
                              {d.active_booking.comment}
                            </p>
                          )}
                        </div>
                      ) : <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      {d.location ? (
                        <div className="flex items-center gap-1 text-xs text-gray-500">
                          <MapPin size={11} className="flex-shrink-0" />{d.location}
                        </div>
                      ) : <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(d.features).map(([k, v]) => (
                          <span key={k} className={`px-1.5 py-0.5 text-xs rounded font-medium ${tagColor(k)}`}>
                            {formatTag(k, v)}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <VersionBadge deployedVersion={d.deployed_version} versionScript={d.version_script} />
                      {!d.version_script && <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        {isFree(d) && (
                          <button onClick={() => setBookDevice2(d)}
                            className="px-3 py-1 text-xs rounded-lg bg-blue-600 text-white hover:bg-blue-700 whitespace-nowrap">
                            Book
                          </button>
                        )}
                        {d.active_booking && (
                          <button onClick={() => setReleaseDevice(d)}
                            className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg border border-amber-300 text-amber-700 hover:bg-amber-50 whitespace-nowrap">
                            <Unlock size={11} /> Release
                          </button>
                        )}
                        <button onClick={() => setEditDevice(d)}
                          className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg border bg-white hover:bg-gray-50 text-gray-600 whitespace-nowrap">
                          <Pencil size={11} /> Modify
                        </button>
                        <button onClick={() => setCloneDevice(d)} title="Clone device"
                          className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg border bg-white hover:bg-gray-50 text-gray-600 whitespace-nowrap">
                          <Copy size={11} /> Clone
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Modals ─────────────────────────────────────────────────────────── */}
      {modal === 'add'      && <AddDeviceModal onClose={() => setModal(null)} />}
      {modal === 'settings' && <SettingsModal onClose={() => setModal(null)} />}
      {modal === 'limit'    && <BookingLimitModal onClose={() => setModal(null)} />}
      {editDevice           && <EditDeviceModal device={editDevice} onClose={() => setEditDevice(null)} />}
      {cloneDevice          && <AddDeviceModal cloneFrom={cloneDevice} onClose={() => setCloneDevice(null)} />}
      {bookDevice2          && <BookModal device={bookDevice2} onClose={() => setBookDevice2(null)} />}
      {releaseDevice        && <ReleaseModal device={releaseDevice} onClose={() => setReleaseDevice(null)} />}
    </div>
  );
}
