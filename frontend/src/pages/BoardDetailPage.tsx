import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Check, Copy, MapPin, Wifi, WifiOff } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  bookBoard,
  extendBooking,
  getBoard,
  getCommands,
  getUsername,
  releaseBooking,
} from '../api/client';
import BoardNotes from '../components/BoardNotes';
import BookingTimer from '../components/BookingTimer';
import ConnectionCommands from '../components/ConnectionCommands';
import StatusBadge from '../components/StatusBadge';
import ToolBadge from '../components/ToolBadge';

function ShellLine({ label, cmd }: { label: string; cmd: string }) {
  const [copied, setCopied] = useState(false);
  function copy() {
    navigator.clipboard.writeText(cmd).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }
  return (
    <div className="bg-gray-900 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-2.5 pb-1.5 border-b border-gray-800">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">{label}</span>
        <button
          onClick={copy}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white transition-colors px-2 py-0.5 rounded hover:bg-gray-700"
          title="Copy"
        >
          {copied ? <><Check size={12} className="text-green-400" /><span className="text-green-400">Copied</span></> : <><Copy size={12} /><span>Copy</span></>}
        </button>
      </div>
      <div className="flex items-start gap-2 px-4 py-3">
        <span className="text-gray-600 select-none font-mono text-sm mt-0.5">$</span>
        <pre className="text-green-400 font-mono text-sm whitespace-pre-wrap break-all flex-1">{cmd}</pre>
      </div>
    </div>
  );
}

export default function BoardDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [duration, setDuration] = useState(4);
  const me = getUsername();

  const { data: board, isLoading } = useQuery({
    queryKey: ['board', id],
    queryFn: () => getBoard(id!),
    refetchInterval: 15_000,
  });

  const myBooking =
    board?.active_booking?.username === me ? board.active_booking : null;

  const { data: commands } = useQuery({
    queryKey: ['commands', myBooking?.id],
    queryFn: () => getCommands(myBooking!.id),
    enabled: !!myBooking,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['board', id] });
    qc.invalidateQueries({ queryKey: ['boards'] });
  };

  const bookMut = useMutation({
    mutationFn: () => bookBoard(id!, duration, '', me),
    onSuccess: invalidate,
  });

  const releaseMut = useMutation({
    mutationFn: () => releaseBooking(myBooking!.id, me),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['commands', myBooking?.id] });
      invalidate();
    },
  });

  const extendMut = useMutation({
    mutationFn: () => extendBooking(myBooking!.id, 1),
    onSuccess: invalidate,
  });

  if (isLoading || !board) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center text-gray-400">
        Loading…
      </div>
    );
  }

  const otherBooking =
    board.active_booking && board.active_booking.username !== me
      ? board.active_booking
      : null;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-3xl mx-auto px-4 py-6">
        <Link
          to="/boards"
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 mb-4"
        >
          <ArrowLeft size={14} /> Back to inventory
        </Link>

        {/* Board header */}
        <div className="bg-white rounded-xl border p-5 mb-4">
          <div className="flex items-start justify-between gap-3 mb-3">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold text-gray-900">{board.name}</h1>
              {board.device_id && (
                <span className="font-mono text-sm bg-gray-100 text-gray-600 px-2 py-0.5 rounded border">
                  {board.device_id}
                </span>
              )}
            </div>
            <StatusBadge
              agentOnline={board.agent_online}
              activeBooking={!!board.active_booking}
              enabled={board.enabled}
            />
          </div>

          {board.description && (
            <p className="text-sm text-gray-600 mb-3">{board.description}</p>
          )}

          <div className="flex flex-wrap gap-4 text-sm text-gray-500">
            {board.location && (
              <div className="flex items-center gap-1">
                <MapPin size={13} />
                {board.location}
              </div>
            )}
            <div className="flex items-center gap-1">
              {board.agent_online ? (
                <Wifi size={13} className="text-green-500" />
              ) : (
                <WifiOff size={13} className="text-gray-400" />
              )}
              {board.host_ip ?? 'No agent'}
            </div>
            {board.serial_number && (
              <div className="flex items-center gap-1">
                <span className="text-xs font-semibold text-gray-400 uppercase">S/N</span>
                <span className="font-mono">{board.serial_number}</span>
              </div>
            )}
            {board.revision && (
              <div className="flex items-center gap-1">
                <span className="text-xs font-semibold text-gray-400 uppercase">Rev</span>
                <span>{board.revision}</span>
              </div>
            )}
          </div>

          {board.tools.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-3">
              {board.tools.map((t) => (
                <ToolBadge key={t.id} tool={t} />
              ))}
            </div>
          )}
        </div>

        {/* Features */}
        {Object.keys(board.features).length > 0 && (
          <div className="bg-white rounded-xl border p-5 mb-4">
            <h2 className="text-sm font-semibold text-gray-700 mb-2">Features</h2>
            <div className="flex flex-wrap gap-2">
              {Object.entries(board.features).map(([k, v]) => (
                <span
                  key={k}
                  className="px-2 py-0.5 text-xs rounded bg-gray-100 text-gray-700"
                >
                  {k}: {String(v)}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Connectivity */}
        {(board.ssh_port > 0 || board.uart_tcp_port > 0 || board.jtag_port > 0 || board.power_script) && (
          <div className="bg-white rounded-xl border p-5 mb-4">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">Connectivity</h2>
            <div className="flex flex-col gap-2">
              {board.ssh_port > 0 && (
                <ShellLine
                  label="SSH"
                  cmd={`ssh ${board.ssh_user}@${board.host_ip ?? 'AGENT_IP'} -p ${board.ssh_port}`}
                />
              )}
              {board.uart_tcp_port > 0 && (
                <ShellLine
                  label="UART"
                  cmd={`telnet ${board.host_ip ?? 'AGENT_IP'} ${board.uart_tcp_port}`}
                />
              )}
              {board.jtag_port > 0 && (
                <ShellLine
                  label="JTAG"
                  cmd={`connect_hw_server -url tcp:${board.host_ip ?? 'AGENT_IP'}:${board.jtag_port}`}
                />
              )}
              {board.power_script && (
                <ShellLine
                  label="Power"
                  cmd={`python3 ${board.power_script} --action on`}
                />
              )}
            </div>
          </div>
        )}

        {/* Notes */}
        <div className="bg-white rounded-xl border p-5 mb-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Notes</h2>
          <BoardNotes boardId={board.id} notes={board.current_notes ?? ''} />
        </div>

        {/* Booking section */}
        <div className="bg-white rounded-xl border p-5 mb-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Booking</h2>

          {myBooking ? (
            <>
              <BookingTimer
                booking={myBooking}
                onExtend={() => extendMut.mutate()}
                onRelease={() => releaseMut.mutate()}
                extending={extendMut.isPending}
                releasing={releaseMut.isPending}
              />
              {bookMut.error && (
                <p className="text-xs text-red-600 mt-2">
                  {(bookMut.error as Error).message}
                </p>
              )}
            </>
          ) : otherBooking ? (
            <div className="text-sm text-gray-600">
              Booked by <strong>{otherBooking.username}</strong> until{' '}
              {new Date(otherBooking.end_time).toLocaleString()}
            </div>
          ) : board.agent_online && board.enabled ? (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <label className="text-xs text-gray-600">Duration</label>
                <select
                  className="border rounded px-2 py-1 text-sm"
                  value={duration}
                  onChange={(e) => setDuration(Number(e.target.value))}
                >
                  {[1, 2, 4, 8, 12, 24].map((h) => (
                    <option key={h} value={h}>
                      {h}h
                    </option>
                  ))}
                </select>
              </div>
              <button
                onClick={() => bookMut.mutate()}
                disabled={bookMut.isPending}
                className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {bookMut.isPending ? 'Booking…' : 'Book Now'}
              </button>
              {bookMut.error && (
                <p className="text-xs text-red-600">
                  {(bookMut.error as Error).message}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-gray-400">Device unavailable for booking</p>
          )}
        </div>

        {/* Connection commands */}
        {commands && (
          <div className="bg-white rounded-xl border p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">
              Connection Commands
            </h2>
            <ConnectionCommands commands={commands} />
          </div>
        )}
      </div>
    </div>
  );
}
