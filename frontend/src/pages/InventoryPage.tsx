import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Clock,
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
  addTool,
  bookBoard,
  createBoard,
  deleteBoard,
  deleteTool,
  getBookingLimit,
  getDefaultUser,
  getServerUrl,
  getToken,
  listBoards,
  releaseBooking,
  setBookingLimit,
  setDefaultUser,
  setServerUrl,
  setToken,
  updateBoard,
} from '../api/client';
import type { BookingLimit } from '../api/client';
import type { BoardCreate, BoardInfo, ToolCreate } from '../api/types';
import StatusBadge from '../components/StatusBadge';
import ToolBadge from '../components/ToolBadge';
import { useStatusSocket } from '../hooks/useStatusSocket';

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

const FIELD_BASIC: [string, keyof BoardCreate][] = [
  ['Name', 'name'],
  ['Serial Number', 'serial_number'],
  ['Revision', 'revision'],
  ['Description', 'description'],
  ['Location', 'location'],
];
const FIELD_ETHERNET: [string, keyof BoardCreate][] = [
  ['Device IP', 'device_ip'],
  ['SSH User', 'ssh_user'],
];
const FIELD_AGENT_TEXT: [string, keyof BoardCreate][] = [
  ['Agent Host IP', 'host_ip'],
  ['Power Script', 'power_script'],
];
const FIELD_AGENT_NUM: [string, keyof BoardCreate][] = [
  ['JTAG Port', 'jtag_port'],
  ['UART TCP Port', 'uart_tcp_port'],
];
const DEFAULT_BOARD: BoardCreate = {
  name: '', serial_number: '', revision: '', description: '',
  location: '', device_ip: '', host_ip: '', features: {}, jtag_port: 3121, uart_tcp_port: 5555,
  ssh_user: 'root', ssh_port: 22, power_script: '', power_args: {},
  enabled: true, current_notes: '',
};
const TOOL_TYPES = ['logic_analyzer', 'power_supply', 'oscilloscope', 'debugger', 'other'];

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
// Add Board Modal
// ─────────────────────────────────────────────────────────────────────────────

function AddBoardModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [username, setUsernameState] = useState(getDefaultUser());
  const [form, setForm] = useState<BoardCreate>(DEFAULT_BOARD);
  const [featuresRaw, setFeaturesRaw] = useState('{}');
  const [hasEthernet, setHasEthernet] = useState(false);
  const [hasAgent, setHasAgent] = useState(false);

  const mut = useMutation({
    mutationFn: () => createBoard({ ...form, features: JSON.parse(featuresRaw) }, username),
    onSuccess: (board) => {
      setDefaultUser(username);
      qc.invalidateQueries({ queryKey: ['boards'] });
      onClose();
      navigate(`/boards/${board.id}`);
    },
  });

  return (
    <Overlay onClose={onClose}>
      <ModalCard title="Add Device" onClose={onClose}>
        <div className="flex flex-col gap-3">
          <Field label="Your username">
            <input className={inputCls} value={username}
              onChange={(e) => setUsernameState(e.target.value)} placeholder="Required" />
          </Field>
          {FIELD_BASIC.map(([label, key]) => (
            <Field key={key as string} label={label}>
              <input type="text" className={inputCls} value={String(form[key] ?? '')}
                onChange={(e) => setForm(f => ({ ...f, [key]: e.target.value }))} />
            </Field>
          ))}
          <Field label="Features (JSON)">
            <textarea className={`${inputCls} font-mono`} rows={3} value={featuresRaw}
              onChange={(e) => setFeaturesRaw(e.target.value)} />
          </Field>

          {/* Ethernet / SSH section */}
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700 border-t pt-3">
            <input type="checkbox" className="accent-blue-600" checked={hasEthernet}
              onChange={(e) => setHasEthernet(e.target.checked)} />
            Has Ethernet / SSH
          </label>
          {hasEthernet && (
            <div className="flex flex-col gap-3 pl-3 border-l-2 border-green-200">
              {FIELD_ETHERNET.map(([label, key]) => (
                <Field key={key as string} label={label}>
                  <input type="text" className={inputCls} value={String(form[key] ?? '')}
                    onChange={(e) => setForm(f => ({ ...f, [key]: e.target.value }))} />
                </Field>
              ))}
              <Field label="SSH Port">
                <input type="number" className={inputCls} value={Number(form.ssh_port)}
                  onChange={(e) => setForm(f => ({ ...f, ssh_port: Number(e.target.value) }))} />
              </Field>
            </div>
          )}

          {/* Agent section */}
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700 border-t pt-3">
            <input type="checkbox" className="accent-blue-600" checked={hasAgent}
              onChange={(e) => setHasAgent(e.target.checked)} />
            Has hardware agent (JTAG · UART · power control)
          </label>
          {hasAgent && (
            <div className="flex flex-col gap-3 pl-3 border-l-2 border-blue-200">
              {FIELD_AGENT_TEXT.map(([label, key]) => (
                <Field key={key as string} label={label}>
                  <input type="text" className={inputCls} value={String(form[key] ?? '')}
                    onChange={(e) => setForm(f => ({ ...f, [key]: e.target.value }))} />
                </Field>
              ))}
              {FIELD_AGENT_NUM.map(([label, key]) => (
                <Field key={key as string} label={label}>
                  <input type="number" className={inputCls} value={Number(form[key])}
                    onChange={(e) => setForm(f => ({ ...f, [key]: Number(e.target.value) }))} />
                </Field>
              ))}
              <Field label="Power Script Args (JSON)">
                <textarea className={`${inputCls} font-mono`} rows={2}
                  value={JSON.stringify(form.power_args ?? {})}
                  onChange={(e) => { try { setForm(f => ({ ...f, power_args: JSON.parse(e.target.value) })); } catch { /* ignore */ } }} />
              </Field>
            </div>
          )}

          <label className="flex items-center gap-2 text-sm border-t pt-3">
            <input type="checkbox" checked={form.enabled}
              onChange={(e) => setForm(f => ({ ...f, enabled: e.target.checked }))} />
            Enabled
          </label>
          {mut.error && <p className="text-xs text-red-600">{(mut.error as Error).message}</p>}
          <ModalActions onCancel={onClose} onConfirm={() => mut.mutate()}
            confirmLabel={mut.isPending ? 'Creating…' : 'Create'}
            confirmDisabled={mut.isPending || !form.name || !username} />
        </div>
      </ModalCard>
    </Overlay>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Edit Board Modal
// ─────────────────────────────────────────────────────────────────────────────

function EditBoardModal({ board, onClose }: { board: BoardInfo; onClose: () => void }) {
  const qc = useQueryClient();
  const [username, setUsernameState] = useState(getDefaultUser());
  const [form, setForm] = useState({
    name: board.name,
    serial_number: board.serial_number,
    revision: board.revision,
    description: board.description,
    location: board.location,
    device_ip: board.device_ip ?? '',
    host_ip: board.host_ip ?? '',
    current_notes: board.current_notes,
    ssh_user: board.ssh_user,
    ssh_port: board.ssh_port,
    jtag_port: board.jtag_port,
    uart_tcp_port: board.uart_tcp_port,
    power_script: board.power_script,
    power_args: board.power_args,
    enabled: board.enabled,
  });
  const [featuresRaw, setFeaturesRaw] = useState(JSON.stringify(board.features, null, 2));
  const [hasEthernet, setHasEthernet] = useState(!!(board.device_ip || board.ssh_port));
  const [hasAgent, setHasAgent] = useState(!!(board.host_ip || board.jtag_port || board.uart_tcp_port));
  const [newTool, setNewTool] = useState<ToolCreate>({ type: 'logic_analyzer', model: '', connection: 'usb', connection_detail: '', notes: '' });
  const [addingTool, setAddingTool] = useState(false);

  const updateMut = useMutation({
    mutationFn: () => {
      let features = board.features;
      try { features = JSON.parse(featuresRaw); } catch { /* keep old */ }
      return updateBoard(board.id, { ...form, features }, username);
    },
    onSuccess: () => { setDefaultUser(username); qc.invalidateQueries({ queryKey: ['boards'] }); onClose(); },
  });
  const addToolMut = useMutation({
    mutationFn: () => addTool(board.id, newTool, username),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['boards'] });
      setAddingTool(false);
      setNewTool({ type: 'logic_analyzer', model: '', connection: 'usb', connection_detail: '', notes: '' });
    },
  });
  const deleteToolMut = useMutation({
    mutationFn: (toolId: string) => deleteTool(toolId, username),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['boards'] }),
  });

  return (
    <Overlay onClose={onClose}>
      <ModalCard title={`Edit — ${board.name}`} onClose={onClose} wide>
        <div className="flex flex-col gap-3">
          <Field label="Your username">
            <input className={inputCls} value={username}
              onChange={(e) => setUsernameState(e.target.value)} placeholder="Required" />
          </Field>
          <Field label="Device ID">
            <span className="font-mono text-sm text-gray-500 bg-gray-50 border rounded-lg px-3 py-1.5">{board.device_id || '—'}</span>
          </Field>
          {([['Name', 'name'], ['Serial Number', 'serial_number'], ['Revision', 'revision'], ['Description', 'description'], ['Location', 'location']] as [string, keyof typeof form][]).map(([label, key]) => (
            <Field key={key} label={label}>
              <input type="text" className={inputCls} value={String(form[key] ?? '')}
                onChange={(e) => setForm(f => ({ ...f, [key]: e.target.value }))} />
            </Field>
          ))}
          <Field label="Features (JSON)">
            <textarea className={`${inputCls} font-mono`} rows={3} value={featuresRaw}
              onChange={(e) => setFeaturesRaw(e.target.value)} />
          </Field>
          <Field label="Notes">
            <textarea className={inputCls} rows={2} value={form.current_notes}
              onChange={(e) => setForm(f => ({ ...f, current_notes: e.target.value }))} />
          </Field>

          {/* Ethernet / SSH section */}
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700 border-t pt-3">
            <input type="checkbox" className="accent-blue-600" checked={hasEthernet}
              onChange={(e) => setHasEthernet(e.target.checked)} />
            Has Ethernet / SSH
          </label>
          {hasEthernet && (
            <div className="flex flex-col gap-3 pl-3 border-l-2 border-green-200">
              {([['Device IP', 'device_ip'], ['SSH User', 'ssh_user']] as [string, keyof typeof form][]).map(([label, key]) => (
                <Field key={key} label={label}>
                  <input type="text" className={inputCls} value={String(form[key] ?? '')}
                    onChange={(e) => setForm(f => ({ ...f, [key]: e.target.value }))} />
                </Field>
              ))}
              <Field label="SSH Port">
                <input type="number" className={inputCls} value={Number(form.ssh_port)}
                  onChange={(e) => setForm(f => ({ ...f, ssh_port: Number(e.target.value) }))} />
              </Field>
            </div>
          )}

          {/* Agent section */}
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700 border-t pt-3">
            <input type="checkbox" className="accent-blue-600" checked={hasAgent}
              onChange={(e) => setHasAgent(e.target.checked)} />
            Has hardware agent (JTAG · UART · power control)
          </label>
          {hasAgent && (
            <div className="flex flex-col gap-3 pl-3 border-l-2 border-blue-200">
              {([['Agent Host IP', 'host_ip'], ['Power Script', 'power_script']] as [string, keyof typeof form][]).map(([label, key]) => (
                <Field key={key} label={label}>
                  <input type="text" className={inputCls} value={String(form[key] ?? '')}
                    onChange={(e) => setForm(f => ({ ...f, [key]: e.target.value }))} />
                </Field>
              ))}
              {([['JTAG Port', 'jtag_port'], ['UART TCP Port', 'uart_tcp_port']] as [string, keyof typeof form][]).map(([label, key]) => (
                <Field key={key} label={label}>
                  <input type="number" className={inputCls} value={Number(form[key])}
                    onChange={(e) => setForm(f => ({ ...f, [key]: Number(e.target.value) }))} />
                </Field>
              ))}
              <Field label="Power Script Args (JSON)">
                <textarea className={`${inputCls} font-mono`} rows={2}
                  value={JSON.stringify(form.power_args ?? {})}
                  onChange={(e) => { try { setForm(f => ({ ...f, power_args: JSON.parse(e.target.value) })); } catch { /* ignore */ } }} />
              </Field>
            </div>
          )}

          <label className="flex items-center gap-2 text-sm border-t pt-3">
            <input type="checkbox" checked={form.enabled}
              onChange={(e) => setForm(f => ({ ...f, enabled: e.target.checked }))} />
            Enabled
          </label>

          {/* Tools */}
          <div className="pt-1 border-t">
            <p className="text-xs font-medium text-gray-600 mb-2">Attached Tools</p>
            <div className="flex flex-wrap gap-1 mb-2">
              {board.tools.map((t) => (
                <div key={t.id} className="flex items-center gap-1">
                  <ToolBadge tool={t} />
                  <button onClick={() => deleteToolMut.mutate(t.id)}
                    className="text-gray-300 hover:text-red-500"><X size={11} /></button>
                </div>
              ))}
            </div>
            {addingTool ? (
              <div className="flex flex-wrap gap-1 items-center">
                <select className="border rounded px-1.5 py-1 text-xs" value={newTool.type}
                  onChange={(e) => setNewTool(t => ({ ...t, type: e.target.value }))}>
                  {TOOL_TYPES.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
                <input className="border rounded px-1.5 py-1 text-xs w-24" placeholder="Model"
                  value={newTool.model} onChange={(e) => setNewTool(t => ({ ...t, model: e.target.value }))} />
                <input className="border rounded px-1.5 py-1 text-xs w-28" placeholder="/dev/ttyUSB1"
                  value={newTool.connection_detail} onChange={(e) => setNewTool(t => ({ ...t, connection_detail: e.target.value }))} />
                <button onClick={() => addToolMut.mutate()}
                  className="px-2 py-1 text-xs bg-blue-600 text-white rounded">Add</button>
                <button onClick={() => setAddingTool(false)}
                  className="text-xs text-gray-400 hover:text-gray-600">Cancel</button>
              </div>
            ) : (
              <button onClick={() => setAddingTool(true)}
                className="flex items-center gap-1 text-xs text-gray-400 hover:text-blue-600">
                <Plus size={11} /> Add tool
              </button>
            )}
          </div>

          {updateMut.error && <p className="text-xs text-red-600">{(updateMut.error as Error).message}</p>}
          <ModalActions onCancel={onClose} onConfirm={() => updateMut.mutate()}
            confirmLabel={updateMut.isPending ? 'Saving…' : 'Save changes'}
            confirmDisabled={updateMut.isPending || !form.name || !username} />
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
  const [url, setUrl] = useState(getServerUrl());
  const [defaultUser, setDefaultUserState] = useState(getDefaultUser());
  const [token, setTokenState] = useState(getToken());

  function save() {
    setServerUrl(url);
    setDefaultUser(defaultUser);
    setToken(token);
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

function BookModal({ board, onClose }: { board: BoardInfo; onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const limit = getBookingLimit();
  const isNever = limit === 'never';
  const maxHours = typeof limit === 'number' ? limit : undefined;
  const [username, setUsernameState] = useState(getDefaultUser());
  const [hours, setHours] = useState(maxHours ? Math.min(4, maxHours) : 4);
  const [comment, setComment] = useState('');

  const mut = useMutation({
    mutationFn: () => bookBoard(board.id, isNever ? 1 : hours, comment, username),
    onSuccess: () => {
      setDefaultUser(username);
      qc.invalidateQueries({ queryKey: ['boards'] });
      onClose();
      navigate(`/boards/${board.id}`);
    },
  });

  return (
    <Overlay onClose={onClose}>
      <ModalCard title="Book device" subtitle={board.name} onClose={onClose}>
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

function ReleaseModal({ board, onClose }: { board: BoardInfo; onClose: () => void }) {
  const qc = useQueryClient();
  const booking = board.active_booking!;
  const [username, setUsernameState] = useState(getDefaultUser());

  const mut = useMutation({
    mutationFn: () => releaseBooking(booking.id, username),
    onSuccess: () => {
      setDefaultUser(username);
      qc.invalidateQueries({ queryKey: ['boards'] });
      onClose();
    },
  });

  return (
    <Overlay onClose={onClose}>
      <ModalCard title={`Release — ${board.name}`} onClose={onClose}>
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
// Shared UI primitives
// ─────────────────────────────────────────────────────────────────────────────

const inputCls = 'border rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500';

function Overlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      {children}
    </div>
  );
}

function ModalCard({ title, subtitle, onClose, wide, children }: {
  title: string; subtitle?: string; onClose: () => void; wide?: boolean; children: React.ReactNode;
}) {
  return (
    <div className={`bg-white rounded-2xl shadow-xl w-full ${wide ? 'max-w-lg' : 'max-w-sm'} max-h-[90vh] overflow-y-auto p-6`}>
      <div className="flex items-start justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold text-gray-900">{title}</h2>
          {subtitle && <p className="text-sm text-gray-500 mt-0.5">{subtitle}</p>}
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 mt-0.5"><X size={18} /></button>
      </div>
      {children}
    </div>
  );
}

function Field({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-gray-600">{label}</span>
      {children}
    </label>
  );
}

function ModalActions({ onCancel, onConfirm, confirmLabel, confirmDisabled }: {
  onCancel: () => void; onConfirm: () => void; confirmLabel: string; confirmDisabled?: boolean;
}) {
  return (
    <div className="flex gap-2 justify-end mt-2">
      <button onClick={onCancel} className="px-4 py-2 text-sm border rounded-lg hover:bg-gray-50">Cancel</button>
      <button onClick={onConfirm} disabled={confirmDisabled}
        className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
        {confirmLabel}
      </button>
    </div>
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
  const [editBoard, setEditBoard] = useState<BoardInfo | null>(null);
  const [bookBoard2, setBookBoard2] = useState<BoardInfo | null>(null);
  const [releaseBoard, setReleaseBoard] = useState<BoardInfo | null>(null);
  const [deleteMode, setDeleteMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useStatusSocket();

  const { data: boards = [], isLoading, refetch, isFetching, isError } = useQuery({
    queryKey: ['boards'],
    queryFn: listBoards,
    refetchInterval: 15_000,
  });

  const deleteMut = useMutation({
    mutationFn: async (ids: string[]) => { for (const id of ids) await deleteBoard(id); },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['boards'] }); setSelected(new Set()); setDeleteMode(false); },
  });

  const filtered = boards.filter((b) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      b.name.toLowerCase().includes(q) ||
      b.device_id.toLowerCase().includes(q) ||
      b.location.toLowerCase().includes(q) ||
      b.description.toLowerCase().includes(q) ||
      (b.active_booking?.username ?? '').toLowerCase().includes(q) ||
      b.tools.some(t => t.type.includes(q) || t.model.toLowerCase().includes(q))
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

  const isFree = (b: BoardInfo) => b.enabled && !b.active_booking;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-6">

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between mb-6 gap-3 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Device Inventory</h1>
            <p className="text-sm text-gray-500">{boards.length} devices registered</p>
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

            {/* Add Board */}
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
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Tools</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wide">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map((b) => (
                  <tr key={b.id}
                    className={`transition-colors ${!b.enabled ? 'opacity-50' : ''} ${selected.has(b.id) ? 'bg-red-50' : 'hover:bg-gray-50'}`}
                  >
                    {deleteMode && (
                      <td className="px-4 py-3">
                        <input type="checkbox" checked={selected.has(b.id)}
                          onChange={() => toggleSelect(b.id)} className="w-4 h-4 accent-red-600" />
                      </td>
                    )}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Link to={`/boards/${b.id}`} className="font-medium text-gray-900 hover:text-blue-600 hover:underline">
                          {b.name}
                        </Link>
                        {b.device_id && (
                          <span className="font-mono text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded border">
                            {b.device_id}
                          </span>
                        )}
                      </div>
                      {b.description && (
                        <p className="text-xs text-gray-400 mt-0.5 max-w-xs truncate">{b.description}</p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge agentOnline={b.agent_online} activeBooking={!!b.active_booking} enabled={b.enabled} />
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
                      ) : <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      {b.location ? (
                        <div className="flex items-center gap-1 text-xs text-gray-500">
                          <MapPin size={11} className="flex-shrink-0" />{b.location}
                        </div>
                      ) : <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {b.tools.map((t) => <ToolBadge key={t.id} tool={t} />)}
                        {b.tools.length === 0 && <span className="text-gray-300">—</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        {isFree(b) && (
                          <button onClick={() => setBookBoard2(b)}
                            className="px-3 py-1 text-xs rounded-lg bg-blue-600 text-white hover:bg-blue-700 whitespace-nowrap">
                            Book
                          </button>
                        )}
                        {b.active_booking && (
                          <button onClick={() => setReleaseBoard(b)}
                            className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg border border-amber-300 text-amber-700 hover:bg-amber-50 whitespace-nowrap">
                            <Unlock size={11} /> Release
                          </button>
                        )}
                        <button onClick={() => setEditBoard(b)}
                          className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg border bg-white hover:bg-gray-50 text-gray-600 whitespace-nowrap">
                          <Pencil size={11} /> Modify
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
      {modal === 'add'      && <AddBoardModal onClose={() => setModal(null)} />}
      {modal === 'settings' && <SettingsModal onClose={() => setModal(null)} />}
      {modal === 'limit'    && <BookingLimitModal onClose={() => setModal(null)} />}
      {editBoard            && <EditBoardModal board={editBoard} onClose={() => setEditBoard(null)} />}
      {bookBoard2           && <BookModal board={bookBoard2} onClose={() => setBookBoard2(null)} />}
      {releaseBoard         && <ReleaseModal board={releaseBoard} onClose={() => setReleaseBoard(null)} />}
    </div>
  );
}
