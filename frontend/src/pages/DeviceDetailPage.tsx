import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Check, Copy, Download, MapPin, Usb, Wifi, WifiOff } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  bookDevice,
  extendBooking,
  getCommands,
  getDevice,
  getUsername,
  releaseBooking,
} from '../api/client';
import DeviceNotes from '../components/DeviceNotes';
import BookingTimer from '../components/BookingTimer';
import StatusBadge from '../components/StatusBadge';

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
  return s;
}

function downloadFile(filename: string, content: string) {
  const blob = new Blob([content], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function uartConnectScript(agentHost: string, uartDevice: string, deviceId: string): string {
  const localPty = `/dev/tty${deviceId}`;
  return `#!/bin/sh
set -eu
# Pre-configured for ${deviceId}

echo "Bridging ${agentHost}:${uartDevice} -> ${localPty}"
echo "Press Ctrl-C to disconnect."

exec sudo socat \\
    "pty,link=${localPty},rawer" \\
    "EXEC:ssh ${agentHost} socat - ${uartDevice}\\,rawer"
`;
}

function sdcardScript(host: string, deviceId: string): string {
  return `#!/bin/sh
set -eu
# Pre-configured for ${deviceId}

HOST="${host}"
LOCAL_MNT="$HOME/sdcard-${deviceId}"

case "$1" in
  open)
    mkdir -p "$LOCAL_MNT"
    REMOTE_MNT="$(ssh "$HOST" sudo /usr/local/sbin/sdcard-acquire | tail -n 1)"
    sshfs "$HOST:$REMOTE_MNT" "$LOCAL_MNT" \\
      -o reconnect \\
      -o ServerAliveInterval=15 \\
      -o ServerAliveCountMax=3
    echo "SD card available at $LOCAL_MNT"
    ;;

  close)
    if mountpoint -q "$LOCAL_MNT"; then
        fusermount -u "$LOCAL_MNT" 2>/dev/null || fusermount3 -u "$LOCAL_MNT"
    fi
    ssh "$HOST" sudo /usr/local/sbin/sdcard-release
    echo "SD card released to DUT"
    ;;

  *)
    echo "Usage: $0 open|close"
    exit 1
    ;;
esac
`;
}

function ShellLine({
  label,
  cmd,
  download,
}: {
  label: string;
  cmd: string;
  download?: { filename: string; content: string };
}) {
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
        <div className="flex items-center gap-1">
          {download && (
            <button
              onClick={() => downloadFile(download.filename, download.content)}
              className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white transition-colors px-2 py-0.5 rounded hover:bg-gray-700"
              title="Download script"
            >
              <Download size={12} /><span>Script</span>
            </button>
          )}
          <button
            onClick={copy}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white transition-colors px-2 py-0.5 rounded hover:bg-gray-700"
            title="Copy"
          >
            {copied ? <><Check size={12} className="text-green-400" /><span className="text-green-400">Copied</span></> : <><Copy size={12} /><span>Copy</span></>}
          </button>
        </div>
      </div>
      <div className="flex items-start gap-2 px-4 py-3">
        <span className="text-gray-600 select-none font-mono text-sm mt-0.5">$</span>
        <pre className="text-green-400 font-mono text-sm whitespace-pre-wrap break-all flex-1">{cmd}</pre>
      </div>
    </div>
  );
}

export default function DeviceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [duration, setDuration] = useState(4);
  const me = getUsername();

  const { data: device, isLoading } = useQuery({
    queryKey: ['device', id],
    queryFn: () => getDevice(id!),
    refetchInterval: 15_000,
  });

  const myBooking =
    device?.active_booking?.username === me ? device.active_booking : null;

  const { data: commands } = useQuery({
    queryKey: ['commands', myBooking?.id],
    queryFn: () => getCommands(myBooking!.id),
    enabled: !!myBooking,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['device', id] });
    qc.invalidateQueries({ queryKey: ['devices'] });
  };

  const bookMut = useMutation({
    mutationFn: () => bookDevice(id!, duration, '', me),
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

  if (isLoading || !device) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center text-gray-400">
        Loading…
      </div>
    );
  }

  const otherBooking =
    device.active_booking && device.active_booking.username !== me
      ? device.active_booking
      : null;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-3xl mx-auto px-4 py-6">
        <Link
          to="/devices"
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 mb-4"
        >
          <ArrowLeft size={14} /> Back to inventory
        </Link>

        {/* Device header */}
        <div className="bg-white rounded-xl border p-5 mb-4">
          <div className="flex items-start justify-between gap-3 mb-3">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold text-gray-900">{device.name}</h1>
              {device.device_id && (
                <span className="font-mono text-sm bg-gray-100 text-gray-600 px-2 py-0.5 rounded border">
                  {device.device_id}
                </span>
              )}
            </div>
            <StatusBadge
              agentOnline={device.agent_online}
              activeBooking={!!device.active_booking}
              enabled={device.enabled}
              hasAgent={!!device.host_ip}
            />
          </div>

          {device.description && (
            <p className="text-sm text-gray-600 mb-3">{device.description}</p>
          )}

          <div className="flex flex-wrap gap-4 text-sm text-gray-500">
            {device.location && (
              <div className="flex items-center gap-1">
                <MapPin size={13} />
                {device.location}
              </div>
            )}
            {device.device_ip && (
              <div className="flex items-center gap-1">
                <span className="text-xs font-semibold text-gray-400 uppercase">IP</span>
                <span className="font-mono">{device.device_ip}</span>
              </div>
            )}
            {device.host_ip && (
              <div className="flex items-center gap-1">
                {device.agent_online ? (
                  <Wifi size={13} className="text-green-500" />
                ) : (
                  <WifiOff size={13} className="text-gray-400" />
                )}
                <span className="text-xs">Agent: {device.host_ip}</span>
              </div>
            )}
            {device.usb_device && (
              <div className="flex items-center gap-1">
                <Usb size={13} className="text-gray-400" />
                <span className="font-mono text-xs">{device.usb_device}</span>
              </div>
            )}
            {!device.device_ip && !device.host_ip && (
              <div className="flex items-center gap-1 text-gray-400">
                <WifiOff size={13} />
                No IP configured
              </div>
            )}
            {device.serial_number && (
              <div className="flex items-center gap-1">
                <span className="text-xs font-semibold text-gray-400 uppercase">S/N</span>
                <span className="font-mono">{device.serial_number}</span>
              </div>
            )}
            {device.revision && (
              <div className="flex items-center gap-1">
                <span className="text-xs font-semibold text-gray-400 uppercase">Rev</span>
                <span>{device.revision}</span>
              </div>
            )}
          </div>
        </div>

        {/* Features */}
        {Object.keys(device.features).length > 0 && (
          <div className="bg-white rounded-xl border p-5 mb-4">
            <h2 className="text-sm font-semibold text-gray-700 mb-2">Features</h2>
            <div className="flex flex-wrap gap-2">
              {Object.entries(device.features).map(([k, v]) => (
                <span key={k} className={`px-2 py-0.5 text-xs rounded-full font-medium ${tagColor(k)}`}>
                  {formatTag(k, v)}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Connectivity */}
        {(device.ssh_port > 0 || (device.uart_device && device.host_ip) || device.jtag_port > 0 || device.power_script || !!device.sdmux_control) && (
          <div className="bg-white rounded-xl border p-5 mb-4">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">Connectivity</h2>
            <div className="flex flex-col gap-2">
              {device.ssh_port > 0 && (
                <ShellLine
                  label="SSH"
                  cmd={`ssh ${device.ssh_user}@${device.device_ip || device.host_ip || 'DEVICE_IP'} -p ${device.ssh_port}`}
                />
              )}
              {device.uart_device && device.host_ip && (
                <ShellLine
                  label="UART"
                  cmd={`sudo socat pty,link=/dev/tty${device.device_id},rawer EXEC:"ssh vivado@${device.host_ip} socat - ${device.uart_device},rawer"`}
                  download={{
                    filename: `uart-connect-${device.device_id}`,
                    content: uartConnectScript(`vivado@${device.host_ip}`, device.uart_device, device.device_id),
                  }}
                />
              )}
              {device.jtag_port > 0 && (
                <ShellLine
                  label="JTAG"
                  cmd={`connect_hw_server -url tcp:${device.host_ip ?? 'AGENT_IP'}:${device.jtag_port}`}
                />
              )}
              {device.power_script && (
                <ShellLine
                  label="Power"
                  cmd={`python3 ${device.power_script} --action on`}
                />
              )}
              {device.sdmux_control && device.host_ip && (
                <ShellLine
                  label="SD Card"
                  cmd="sdcard open|close"
                  download={{
                    filename: `sdcard-${device.device_id}`,
                    content: sdcardScript(`vivado@${device.host_ip}`, device.device_id),
                  }}
                />
              )}
              {commands?.vivado_tcl && (
                <ShellLine label="Vivado TCL" cmd={commands.vivado_tcl} />
              )}
            </div>
          </div>
        )}

        {/* Notes */}
        <div className="bg-white rounded-xl border p-5 mb-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Notes</h2>
          <DeviceNotes deviceId={device.id} notes={device.current_notes ?? ''} />
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
          ) : device.enabled ? (
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
            <p className="text-sm text-gray-400">Device is disabled</p>
          )}
        </div>

      </div>
    </div>
  );
}
