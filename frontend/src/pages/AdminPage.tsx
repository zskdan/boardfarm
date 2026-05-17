import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  addTool,
  createBoard,
  deleteBoard,
  deleteTool,
  listBoards,
  updateBoard,
} from '../api/client';
import type { BoardCreate, ToolCreate } from '../api/types';
import ToolBadge from '../components/ToolBadge';

const DEFAULT_BOARD: BoardCreate = {
  name: '',
  description: '',
  location: '',
  features: {},
  jtag_port: 3121,
  uart_tcp_port: 5555,
  ssh_user: 'root',
  ssh_port: 22,
  power_script: '',
  power_args: {},
  enabled: true,
  current_notes: '',
};

function AddBoardModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [form, setForm] = useState<BoardCreate>(DEFAULT_BOARD);
  const [featuresRaw, setFeaturesRaw] = useState('{}');

  const mut = useMutation({
    mutationFn: () =>
      createBoard({ ...form, features: JSON.parse(featuresRaw) }),
    onSuccess: (board) => {
      qc.invalidateQueries({ queryKey: ['boards'] });
      onClose();
      navigate(`/boards/${board.id}`);
    },
  });

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <h2 className="text-lg font-bold mb-4">Add Board</h2>
        <div className="flex flex-col gap-3">
          {[
            ['Name', 'name', 'text'],
            ['Description', 'description', 'text'],
            ['Location', 'location', 'text'],
            ['SSH User', 'ssh_user', 'text'],
            ['Power Script', 'power_script', 'text'],
          ].map(([label, key, type]) => (
            <label key={key} className="flex flex-col gap-1">
              <span className="text-xs font-medium text-gray-600">{label}</span>
              <input
                type={type}
                className="border rounded-lg px-3 py-1.5 text-sm"
                value={String(form[key as keyof BoardCreate] ?? '')}
                onChange={(e) =>
                  setForm((f) => ({ ...f, [key]: e.target.value }))
                }
              />
            </label>
          ))}
          {[
            ['JTAG Port', 'jtag_port'],
            ['UART TCP Port', 'uart_tcp_port'],
            ['SSH Port', 'ssh_port'],
          ].map(([label, key]) => (
            <label key={key} className="flex flex-col gap-1">
              <span className="text-xs font-medium text-gray-600">{label}</span>
              <input
                type="number"
                className="border rounded-lg px-3 py-1.5 text-sm"
                value={Number(form[key as keyof BoardCreate])}
                onChange={(e) =>
                  setForm((f) => ({ ...f, [key]: Number(e.target.value) }))
                }
              />
            </label>
          ))}
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-gray-600">
              Features (JSON)
            </span>
            <textarea
              className="border rounded-lg px-3 py-1.5 text-sm font-mono"
              rows={3}
              value={featuresRaw}
              onChange={(e) => setFeaturesRaw(e.target.value)}
            />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
            />
            Enabled
          </label>
          {mut.error && (
            <p className="text-xs text-red-600">{(mut.error as Error).message}</p>
          )}
          <div className="flex gap-2 justify-end mt-2">
            <button
              onClick={onClose}
              className="px-4 py-1.5 border rounded-lg text-sm hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={() => mut.mutate()}
              disabled={mut.isPending || !form.name}
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
      updateBoard(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['boards'] }),
  });

  const deleteMut = useMutation({
    mutationFn: deleteBoard,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['boards'] }),
  });

  const addToolMut = useMutation({
    mutationFn: ({ boardId, tool }: { boardId: string; tool: ToolCreate }) =>
      addTool(boardId, tool),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['boards'] });
      setAddingTool(null);
    },
  });

  const deleteToolMut = useMutation({
    mutationFn: deleteTool,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['boards'] }),
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
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Admin</h1>
          <button
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-1 px-3 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
          >
            <Plus size={14} /> Add Board
          </button>
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
                    if (confirm(`Delete board "${board.name}"?`))
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
                  className="px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded"
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
                      className="text-gray-300 hover:text-red-500"
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
                      className="text-xs px-2 py-0.5 bg-blue-600 text-white rounded"
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
