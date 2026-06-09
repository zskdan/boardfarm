import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  addTool,
  createBoard,
  deleteBoard,
  deleteTool,
  getDefaultUser,
  listBoards,
  setDefaultUser,
  updateBoard,
} from '../api/client';
import type { BoardCreate, ToolCreate } from '../api/types';
import ToolBadge from '../components/ToolBadge';

function parseAddr(addr: string, defaultPort: number): { ip: string; port: number } {
  const last = addr.lastIndexOf(':');
  if (last === -1) return { ip: addr.trim(), port: defaultPort };
  return { ip: addr.slice(0, last).trim(), port: parseInt(addr.slice(last + 1)) || defaultPort };
}

function ServiceSection({
  label,
  enabled,
  onToggle,
  children,
}: {
  label: string;
  enabled: boolean;
  onToggle: (v: boolean) => void;
  children: React.ReactNode;
}) {
  return (
    <div className="border rounded-lg p-3 flex flex-col gap-2">
      <label className="flex items-center gap-2 cursor-pointer select-none">
        <input type="checkbox" checked={enabled} onChange={(e) => onToggle(e.target.checked)} />
        <span className="text-sm font-medium text-gray-700">{label}</span>
      </label>
      {enabled && <div className="flex flex-col gap-2 pl-6">{children}</div>}
    </div>
  );
}

function AddBoardModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [username, setUsername] = useState(getDefaultUser());
  const [name, setName] = useState('');
  const [serialNumber, setSerialNumber] = useState('');
  const [revision, setRevision] = useState('');
  const [description, setDescription] = useState('');
  const [location, setLocation] = useState('');
  const [notes, setNotes] = useState('');
  const [featuresRaw, setFeaturesRaw] = useState('{}');
  const [enabled, setEnabled] = useState(true);

  const [ssh, setSsh] = useState({ enabled: true, addr: '', user: 'root' });
  const [uart, setUart] = useState({ enabled: true, addr: '' });
  const [jtag, setJtag] = useState({ enabled: true, addr: '' });
  const [power, setPower] = useState({ enabled: false, script: '', args: '{}' });

  const mut = useMutation({
    mutationFn: () => {
      const sshP = ssh.enabled ? parseAddr(ssh.addr, 22) : { ip: '', port: 0 };
      const uartP = uart.enabled ? parseAddr(uart.addr, 5555) : { ip: '', port: 0 };
      const jtagP = jtag.enabled ? parseAddr(jtag.addr, 3121) : { ip: '', port: 0 };
      const host_ip = sshP.ip || uartP.ip || jtagP.ip || undefined;
      return createBoard(
        {
          name,
          serial_number: serialNumber,
          revision,
          description,
          location,
          current_notes: notes,
          host_ip,
          features: JSON.parse(featuresRaw || '{}'),
          enabled,
          ssh_user: ssh.enabled ? ssh.user || 'root' : 'root',
          ssh_port: sshP.port,
          uart_tcp_port: uartP.port,
          jtag_port: jtagP.port,
          power_script: power.enabled ? power.script : '',
          power_args: power.enabled ? JSON.parse(power.args || '{}') : {},
        },
        username,
      );
    },
    onSuccess: (board) => {
      setDefaultUser(username);
      qc.invalidateQueries({ queryKey: ['boards'] });
      onClose();
      navigate(`/boards/${board.id}`);
    },
  });

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <h2 className="text-lg font-bold mb-4">Add Device</h2>
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-gray-600">
              Your username <span className="text-red-500">*</span>
            </span>
            <input
              className="border rounded-lg px-3 py-1.5 text-sm"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Required"
            />
          </label>

          {[
            ['Name *', name, setName],
            ['Description', description, setDescription],
            ['Location', location, setLocation],
          ].map(([label, val, setter]) => (
            <label key={label as string} className="flex flex-col gap-1">
              <span className="text-xs font-medium text-gray-600">{label as string}</span>
              <input
                className="border rounded-lg px-3 py-1.5 text-sm"
                value={val as string}
                onChange={(e) => (setter as (v: string) => void)(e.target.value)}
              />
            </label>
          ))}

          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-gray-600">Serial Number</span>
            <input
              className="border rounded-lg px-3 py-1.5 text-sm font-mono"
              value={serialNumber}
              onChange={(e) => setSerialNumber(e.target.value)}
              placeholder="e.g. SN-20240001"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-gray-600">Revision</span>
            <input
              className="border rounded-lg px-3 py-1.5 text-sm"
              value={revision}
              onChange={(e) => setRevision(e.target.value)}
              placeholder="e.g. 1.2"
            />
          </label>

          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide pt-1">
            Services
          </span>

          <ServiceSection label="SSH" enabled={ssh.enabled} onToggle={(v) => setSsh((s) => ({ ...s, enabled: v }))}>
            <input
              type="text"
              className="border rounded px-2 py-1.5 text-sm font-mono w-full"
              placeholder="192.168.1.5:22"
              value={ssh.addr}
              onChange={(e) => setSsh((s) => ({ ...s, addr: e.target.value }))}
            />
            <input
              type="text"
              className="border rounded px-2 py-1.5 text-sm w-full"
              placeholder="SSH user (default: root)"
              value={ssh.user}
              onChange={(e) => setSsh((s) => ({ ...s, user: e.target.value }))}
            />
          </ServiceSection>

          <ServiceSection label="UART" enabled={uart.enabled} onToggle={(v) => setUart((s) => ({ ...s, enabled: v }))}>
            <input
              type="text"
              className="border rounded px-2 py-1.5 text-sm font-mono w-full"
              placeholder="192.168.1.5:5555"
              value={uart.addr}
              onChange={(e) => setUart((s) => ({ ...s, addr: e.target.value }))}
            />
          </ServiceSection>

          <ServiceSection label="JTAG" enabled={jtag.enabled} onToggle={(v) => setJtag((s) => ({ ...s, enabled: v }))}>
            <input
              type="text"
              className="border rounded px-2 py-1.5 text-sm font-mono w-full"
              placeholder="192.168.1.5:3121"
              value={jtag.addr}
              onChange={(e) => setJtag((s) => ({ ...s, addr: e.target.value }))}
            />
          </ServiceSection>

          <ServiceSection label="Power Control" enabled={power.enabled} onToggle={(v) => setPower((s) => ({ ...s, enabled: v }))}>
            <input
              type="text"
              className="border rounded px-2 py-1.5 text-sm w-full"
              placeholder="Script path (e.g. power/usb_relay.py)"
              value={power.script}
              onChange={(e) => setPower((s) => ({ ...s, script: e.target.value }))}
            />
            <textarea
              className="border rounded px-2 py-1.5 text-sm font-mono w-full"
              rows={2}
              placeholder='{"relay_id": 1}'
              value={power.args}
              onChange={(e) => setPower((s) => ({ ...s, args: e.target.value }))}
            />
          </ServiceSection>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-gray-600">Features (JSON)</span>
            <textarea
              className="border rounded-lg px-3 py-1.5 text-sm font-mono"
              rows={2}
              value={featuresRaw}
              onChange={(e) => setFeaturesRaw(e.target.value)}
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-gray-600">Notes</span>
            <textarea
              className="border rounded-lg px-3 py-1.5 text-sm"
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            Enabled
          </label>

          {mut.error && (
            <p className="text-xs text-red-600">{(mut.error as Error).message}</p>
          )}
          <div className="flex gap-2 justify-end mt-2">
            <button onClick={onClose} className="px-4 py-1.5 border rounded-lg text-sm hover:bg-gray-50">
              Cancel
            </button>
            <button
              onClick={() => mut.mutate()}
              disabled={mut.isPending || !name || !username}
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

export default function AdminPage() {
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [username, setUsernameState] = useState(getDefaultUser());
  const [editLocation, setEditLocation] = useState<Record<string, string>>({});
  const [addingTool, setAddingTool] = useState<string | null>(null);
  const [newTool, setNewTool] = useState<ToolCreate>({
    type: 'logic_analyzer',
    model: '',
    connection: 'usb',
    connection_detail: '',
    notes: '',
  });

  const { data: boards = [] } = useQuery({
    queryKey: ['boards'],
    queryFn: listBoards,
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<BoardCreate> }) =>
      updateBoard(id, data, username),
    onSuccess: () => {
      setDefaultUser(username);
      qc.invalidateQueries({ queryKey: ['boards'] });
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteBoard(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['boards'] }),
  });

  const addToolMut = useMutation({
    mutationFn: ({ boardId, tool }: { boardId: string; tool: ToolCreate }) =>
      addTool(boardId, tool, username),
    onSuccess: () => {
      setDefaultUser(username);
      qc.invalidateQueries({ queryKey: ['boards'] });
      setAddingTool(null);
    },
  });

  const deleteToolMut = useMutation({
    mutationFn: (id: string) => deleteTool(id, username),
    onSuccess: () => {
      setDefaultUser(username);
      qc.invalidateQueries({ queryKey: ['boards'] });
    },
  });

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-5xl mx-auto px-4 py-6">
        <Link
          to="/boards"
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 mb-4"
        >
          <ArrowLeft size={14} /> Back to inventory
        </Link>
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-bold text-gray-900">Admin</h1>
          <button
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-1 px-3 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
          >
            <Plus size={14} /> Add Device
          </button>
        </div>

        {/* Acting-as username — used for all inline operations */}
        <div className="bg-white rounded-xl border px-4 py-3 mb-6 flex items-center gap-3">
          <span className="text-xs font-medium text-gray-500 whitespace-nowrap">Acting as</span>
          <input
            className="border rounded-lg px-3 py-1.5 text-sm flex-1 max-w-xs"
            value={username}
            onChange={(e) => {
              setUsernameState(e.target.value);
              setDefaultUser(e.target.value);
            }}
            placeholder="Your username (required for writes)"
          />
        </div>

        <div className="flex flex-col gap-4">
          {boards.map((board) => (
            <div key={board.id} className="bg-white rounded-xl border p-4">
              <div className="flex items-start justify-between gap-2 mb-3">
                <div>
                  <Link
                    to={`/boards/${board.id}`}
                    className="font-semibold text-gray-900 hover:underline"
                  >
                    {board.name}
                  </Link>
                  <p className="text-xs text-gray-400 font-mono">{board.id}</p>
                </div>
                <button
                  onClick={() => {
                    if (confirm(`Delete device "${board.name}"?`))
                      deleteMut.mutate(board.id);
                  }}
                  className="text-red-400 hover:text-red-600"
                >
                  <Trash2 size={15} />
                </button>
              </div>

              {/* Location edit */}
              <div className="flex items-center gap-2 mb-3">
                <input
                  className="border rounded px-2 py-1 text-sm flex-1"
                  placeholder="Location (e.g. Lab A / Rack 2)"
                  value={editLocation[board.id] ?? board.location}
                  onChange={(e) =>
                    setEditLocation((p) => ({ ...p, [board.id]: e.target.value }))
                  }
                />
                <button
                  onClick={() =>
                    updateMut.mutate({
                      id: board.id,
                      data: { location: editLocation[board.id] ?? board.location },
                    })
                  }
                  disabled={!username}
                  className="px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded disabled:opacity-40"
                >
                  Save
                </button>
              </div>

              {/* Tools */}
              <div className="flex flex-wrap gap-1 mb-2">
                {board.tools.map((t) => (
                  <div key={t.id} className="flex items-center gap-1">
                    <ToolBadge tool={t} />
                    <button
                      onClick={() => deleteToolMut.mutate(t.id)}
                      disabled={!username}
                      className="text-gray-300 hover:text-red-500 disabled:opacity-40"
                    >
                      <Trash2 size={10} />
                    </button>
                  </div>
                ))}
                {addingTool === board.id ? (
                  <div className="flex gap-1 items-center flex-wrap">
                    <select
                      className="border rounded px-1 py-0.5 text-xs"
                      value={newTool.type}
                      onChange={(e) =>
                        setNewTool((t) => ({ ...t, type: e.target.value }))
                      }
                    >
                      {[
                        'logic_analyzer',
                        'power_supply',
                        'oscilloscope',
                        'debugger',
                        'other',
                      ].map((o) => (
                        <option key={o} value={o}>
                          {o}
                        </option>
                      ))}
                    </select>
                    <input
                      className="border rounded px-1 py-0.5 text-xs w-24"
                      placeholder="Model"
                      value={newTool.model}
                      onChange={(e) =>
                        setNewTool((t) => ({ ...t, model: e.target.value }))
                      }
                    />
                    <input
                      className="border rounded px-1 py-0.5 text-xs w-28"
                      placeholder="/dev/ttyUSB1"
                      value={newTool.connection_detail}
                      onChange={(e) =>
                        setNewTool((t) => ({ ...t, connection_detail: e.target.value }))
                      }
                    />
                    <button
                      onClick={() =>
                        addToolMut.mutate({ boardId: board.id, tool: newTool })
                      }
                      disabled={!username}
                      className="text-xs px-2 py-0.5 bg-blue-600 text-white rounded disabled:opacity-40"
                    >
                      Add
                    </button>
                    <button
                      onClick={() => setAddingTool(null)}
                      className="text-xs text-gray-400 hover:text-gray-600"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setAddingTool(board.id)}
                    className="flex items-center gap-0.5 text-xs text-gray-400 hover:text-blue-600"
                  >
                    <Plus size={11} /> tool
                  </button>
                )}
              </div>

              {/* Toggle enabled */}
              <label className="flex items-center gap-2 text-xs text-gray-500">
                <input
                  type="checkbox"
                  checked={board.enabled}
                  onChange={(e) =>
                    updateMut.mutate({
                      id: board.id,
                      data: { enabled: e.target.checked },
                    })
                  }
                />
                Enabled
              </label>
            </div>
          ))}
        </div>
      </div>

      {showAdd && <AddBoardModal onClose={() => setShowAdd(false)} />}
    </div>
  );
}
