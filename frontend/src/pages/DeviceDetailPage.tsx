import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import React, { useEffect, useRef } from 'react';
import { ArrowLeft, Check, Copy, Download, MapPin, Pencil, Usb, Wifi, WifiOff, X } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  bookDevice,
  extendBooking,
  getDevice,
  getRedeployInfo,
  getUsername,
  redeployDevice,
  releaseBooking,
} from '../api/client';
import DeviceNotes from '../components/DeviceNotes';
import BookingTimer from '../components/BookingTimer';
import StatusBadge from '../components/StatusBadge';
import { EditDeviceModal } from '../components/EditDeviceModal';

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

function sdcardScript(host: string, deviceId: string, sdmuxControl: string): string {
  return `#!/bin/sh
set -eu
# Pre-configured for ${deviceId}
# Override at runtime: AGENT_HOST=... DEVICE_ID=... SDMUX_CONTROL=... ./sdcard-${deviceId} open

AGENT_HOST="\${AGENT_HOST:-${host}}"
DEVICE_ID="\${DEVICE_ID:-${deviceId}}"
SDMUX_CONTROL="\${SDMUX_CONTROL:-${sdmuxControl}}"
ACTION="\${1:?Usage: \$0 open|close|status}"

LOCAL_MNT="\$HOME/sdcard-\${DEVICE_ID}"

case "\$ACTION" in
  open)
    mkdir -p "\$LOCAL_MNT"
    REMOTE_MNT="\$(ssh "\$AGENT_HOST" sudo /opt/boardfarm/agent/sdcard-manager open "\$SDMUX_CONTROL" | tail -n 1)"
    sshfs "\$AGENT_HOST:\$REMOTE_MNT" "\$LOCAL_MNT" \\
      -o reconnect \\
      -o ServerAliveInterval=15 \\
      -o ServerAliveCountMax=3
    echo "SD card available at \$LOCAL_MNT"
    ;;

  close)
    if mountpoint -q "\$LOCAL_MNT" 2>/dev/null; then
      fusermount -u "\$LOCAL_MNT" 2>/dev/null || fusermount3 -u "\$LOCAL_MNT"
    fi
    ssh "\$AGENT_HOST" sudo /opt/boardfarm/agent/sdcard-manager close
    echo "SD card released to DUT"
    ;;

  status)
    if mountpoint -q "\$LOCAL_MNT" 2>/dev/null; then
      echo "open — mounted at \$LOCAL_MNT"
    else
      echo "closed"
    fi
    ;;

  *)
    echo "Usage: \$0 open|close|status" >&2
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

// ─── Version parsing helpers ─────────────────────────────────────────────────

interface ParsedVersion {
  curSha: string;
  isClean: boolean | null;
  refSha: string | undefined;
  detail: string;
}

function parseDeployedVersion(raw: string): ParsedVersion {
  const nl = raw.indexOf('\n');
  const firstLine = nl === -1 ? raw : raw.slice(0, nl);
  const detail = nl === -1 ? '' : raw.slice(nl + 1);
  const parts = firstLine.split(':');
  if (parts.length >= 2 && (parts[1] === 'clean' || parts[1] === 'dirty')) {
    return {
      curSha: parts[0],
      isClean: parts[1] === 'clean',
      refSha: parts[2],
      detail,
    };
  }
  return { curSha: firstLine, isClean: null, refSha: undefined, detail };
}

function DiffContent({ isClean, detail }: { isClean: boolean | null; detail: string }) {
  if (!detail) {
    return <p className="text-sm text-gray-400 italic">No content available.</p>;
  }

  if (isClean !== false) {
    return (
      <pre className="text-sm font-mono text-gray-700 whitespace-pre-wrap break-all leading-relaxed">
        {detail}
      </pre>
    );
  }

  // Parse unified diff produced by `diff -U 99999 ref current`
  const lines = detail.split('\n');
  const hunkStart = lines.findIndex(l => l.startsWith('@@'));
  const diffLines = hunkStart >= 0 ? lines.slice(hunkStart + 1) : lines;

  const nodes: React.ReactNode[] = [];
  let i = 0;
  while (i < diffLines.length) {
    const line = diffLines[i];
    if (line.startsWith(' ')) {
      nodes.push(
        <div key={i} className="font-mono text-sm text-gray-700 px-2 py-px leading-5">
          {line.slice(1)}
        </div>,
      );
      i++;
    } else if (line.startsWith('-')) {
      const removed: string[] = [];
      while (i < diffLines.length && diffLines[i].startsWith('-')) {
        removed.push(diffLines[i].slice(1));
        i++;
      }
      const added: string[] = [];
      while (i < diffLines.length && diffLines[i].startsWith('+')) {
        added.push(diffLines[i].slice(1));
        i++;
      }
      const maxLen = Math.max(removed.length, added.length);
      for (let j = 0; j < maxLen; j++) {
        const cur = j < added.length ? added[j] : undefined;
        const ref = j < removed.length ? removed[j] : undefined;
        if (cur !== undefined) {
          nodes.push(
            <div key={`a${i}-${j}`} className="flex flex-col">
              <div className="font-mono text-sm bg-red-50 text-red-700 px-2 py-px leading-5 border-l-2 border-red-400">
                {cur}
              </div>
              {ref !== undefined && (
                <div className="font-mono text-xs text-gray-400 italic px-4 py-0 leading-4">
                  ref: {ref}
                </div>
              )}
            </div>,
          );
        } else if (ref !== undefined) {
          nodes.push(
            <div key={`d${i}-${j}`} className="font-mono text-sm text-red-400 line-through px-2 py-px leading-5 border-l-2 border-red-200 opacity-70">
              {ref}
            </div>,
          );
        }
      }
    } else if (line.startsWith('+')) {
      nodes.push(
        <div key={i} className="font-mono text-sm bg-red-50 text-red-700 px-2 py-px leading-5 border-l-2 border-red-400">
          {line.slice(1)}
        </div>,
      );
      i++;
    } else {
      i++;
    }
  }

  return <div className="flex flex-col">{nodes}</div>;
}

// ─────────────────────────────────────────────────────────────────────────────

export default function DeviceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [duration, setDuration] = useState(4);
  const [showVersionDetail, setShowVersionDetail] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [redeployResult, setRedeployResult] = useState<{ ok: boolean; stdout: string; stderr: string } | null>(null);
  const [redeployProgress, setRedeployProgress] = useState<number>(0);
  const progressTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const me = getUsername();

  const { data: device, isLoading } = useQuery({
    queryKey: ['device', id],
    queryFn: () => getDevice(id!),
    refetchInterval: 15_000,
  });

  const myBooking =
    device?.active_booking?.username === me ? device.active_booking : null;

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
    onSuccess: invalidate,
  });

  const extendMut = useMutation({
    mutationFn: () => extendBooking(myBooking!.id, 1),
    onSuccess: invalidate,
  });

  const startProgressBar = (scriptLines: number) => {
    setRedeployProgress(0);
    // Each script line ≈ 2 s; tick every 200 ms → increment = 100 / (lines * 10 ticks/s * 2s)
    const totalTicks = scriptLines * 10;
    let tick = 0;
    progressTimer.current = setInterval(() => {
      tick += 1;
      // Ease toward 95%: progress = 95 * (1 - e^(-3 * tick/totalTicks))
      const pct = 95 * (1 - Math.exp(-3 * tick / totalTicks));
      setRedeployProgress(Math.min(pct, 95));
    }, 200);
  };

  const stopProgressBar = (success: boolean) => {
    if (progressTimer.current) {
      clearInterval(progressTimer.current);
      progressTimer.current = null;
    }
    setRedeployProgress(success ? 100 : 0);
  };

  useEffect(() => () => { if (progressTimer.current) clearInterval(progressTimer.current); }, []);

  const redeployMut = useMutation({
    mutationFn: async () => {
      const info = await getRedeployInfo(id!, me).catch(() => ({ exists: true, script_lines: 10 }));
      startProgressBar(info.script_lines);
      return redeployDevice(id!, me);
    },
    onSuccess: (result) => {
      stopProgressBar(true);
      setRedeployResult(result);
      if (result.ok) invalidate();
    },
    onError: () => stopProgressBar(false),
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

  // Inline Redeploy button + progress bar, reused in both the header row and the standalone card
  const RedeployBtn = ({ small, disabledReason }: { small?: boolean; disabledReason?: string }) => (
    <div className={`flex flex-col gap-1 ${small ? '' : 'w-full'}`}>
      <button
        onClick={() => { setRedeployResult(null); setRedeployProgress(0); redeployMut.mutate(); }}
        disabled={redeployMut.isPending || !!disabledReason}
        className={small
          ? 'text-xs px-2 py-0.5 rounded border border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors'
          : 'text-sm px-3 py-1.5 rounded-lg border border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap'}
        title={disabledReason ?? `Run: ${device.redeployment_script}`}
      >
        {redeployMut.isPending ? 'Redeploying…' : '↺ Redeploy'}
      </button>
      {redeployMut.isPending && (
        <div className={`bg-gray-200 rounded-full overflow-hidden ${small ? 'h-1 w-24' : 'h-1.5 w-full'}`}>
          <div
            className="h-full bg-violet-500 transition-all duration-200 ease-out"
            style={{ width: `${redeployProgress}%` }}
          />
        </div>
      )}
    </div>
  );

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
            <div className="flex items-center gap-2 flex-shrink-0">
              <StatusBadge
                agentOnline={device.agent_online}
                activeBooking={!!device.active_booking}
                enabled={device.enabled}
                hasAgent={!!device.host_ip}
              />
              <button
                onClick={() => setShowEdit(true)}
                className="flex items-center gap-1 px-2.5 py-1 text-xs border rounded-lg text-gray-600 hover:bg-gray-50 hover:text-blue-600"
                title="Modify device"
              >
                <Pencil size={12} /> Modify
              </button>
            </div>
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
                <span className="text-xs">
                  Agent: {device.host_ip}
                  {device.agent_version && (
                    <span className="font-mono text-gray-400"> ({device.agent_version})</span>
                  )}
                </span>
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
            {device.version_script && (() => {
              const vp = parseDeployedVersion(device.deployed_version || '');
              if (!device.deployed_version || !vp.curSha) {
                return (
                  <div className="flex items-center gap-2 flex-wrap">
                    <div className="flex items-center gap-1">
                      <span className="text-xs font-semibold text-gray-400 uppercase">Deployed</span>
                      <span className="font-mono text-xs px-1.5 py-0.5 rounded border bg-gray-50 text-gray-400 border-gray-200">
                        pending…
                      </span>
                    </div>
                    {device.redeployment_script && device.active_booking?.username === me && (
                      <RedeployBtn small disabledReason="Version not yet checked — cannot determine if redeployment is needed" />
                    )}
                  </div>
                );
              }
              const badgeCls = vp.isClean === true
                ? 'bg-green-50 text-green-700 border-green-200 hover:bg-green-100'
                : vp.isClean === false
                  ? 'bg-red-50 text-red-700 border-red-200 hover:bg-red-100'
                  : 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100';
              return (
                <div className="flex items-center gap-2 flex-wrap">
                  <div className="flex items-center gap-1">
                    <span className="text-xs font-semibold text-gray-400 uppercase">Deployed</span>
                    <button
                      onClick={() => setShowVersionDetail(true)}
                      className={`font-mono text-xs px-1.5 py-0.5 rounded border flex items-center gap-1 transition-colors ${badgeCls}`}
                      title="Click to view version details"
                    >
                      {vp.curSha}
                      {vp.isClean === true && <span className="text-green-600">✓</span>}
                      {vp.isClean === false && (
                        <>
                          <span className="text-red-600">✗</span>
                          {vp.refSha && (
                            <span className="opacity-60 text-xs">ref:{vp.refSha}</span>
                          )}
                        </>
                      )}
                    </button>
                  </div>
                  {device.redeployment_script && device.active_booking?.username === me && (
                    <RedeployBtn small disabledReason={vp.isClean !== false ? 'Deployed version matches reference — redeployment not needed' : undefined} />
                  )}
                </div>
              );
            })()}
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

        {/* Connectivity */}
        {(device.ssh_port > 0 || (device.uart_device && device.host_ip) || device.jtag_port > 0 || device.power_script || !!device.sdmux_control) && (
          <div className="bg-white rounded-xl border p-5 mb-4">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">Connectivity</h2>
            <div className="flex flex-col gap-2">
              {device.ssh_port > 0 && (() => {
                const isSelfHosted = !!(device.host_ip && device.device_ip && device.host_ip === device.device_ip);
                const hasExternalAgent = !!(device.host_ip && !isSelfHosted);
                return (
                  <div className="flex flex-col gap-1.5">
                    {hasExternalAgent && (
                      <label className="flex items-center gap-1.5 text-xs text-gray-500 select-none px-0.5 cursor-default">
                        <input
                          type="checkbox"
                          checked
                          readOnly
                          className="rounded cursor-default"
                        />
                        Through agent
                      </label>
                    )}
                    <ShellLine
                      label="SSH"
                      cmd={hasExternalAgent
                        ? `ssh -J vivado@${device.host_ip} ${device.ssh_user}@${device.device_ip || 'DEVICE_IP'} -p ${device.ssh_port}`
                        : `ssh ${device.ssh_user}@${device.device_ip || device.host_ip || 'DEVICE_IP'} -p ${device.ssh_port}`
                      }
                    />
                  </div>
                );
              })()}
              {device.uart_device && device.host_ip && (
                <>
                  <ShellLine
                    label="UART (socat)"
                    cmd={`sudo socat pty,link=/dev/tty${device.device_id},rawer EXEC:"ssh vivado@${device.host_ip} socat - ${device.uart_device},rawer"`}
                  />
                  <ShellLine
                    label="UART (script)"
                    cmd={`./uart-connect-${device.device_id}`}
                    download={{
                      filename: `uart-connect-${device.device_id}`,
                      content: uartConnectScript(`vivado@${device.host_ip}`, device.uart_device, device.device_id),
                    }}
                  />
                </>
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
                  cmd={`./sdcard-${device.device_id} open|close|status`}
                  download={{
                    filename: `sdcard-${device.device_id}`,
                    content: sdcardScript(`vivado@${device.host_ip}`, device.device_id, device.sdmux_control),
                  }}
                />
              )}
            </div>
          </div>
        )}

        {/* Notes */}
        <div className="bg-white rounded-xl border p-5 mb-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Notes</h2>
          <DeviceNotes deviceId={device.id} notes={device.current_notes ?? ''} />
        </div>

        {/* Parameters */}
        {(() => {
          const rows: { label: string; value: string; mono?: boolean }[] = [];
          if (device.device_ip) rows.push({ label: 'Device IP', value: device.device_ip, mono: true });
          if (device.ssh_port > 0) rows.push({ label: 'SSH', value: `${device.ssh_user}@… :${device.ssh_port}`, mono: true });
          if (device.host_ip) {
            const selfHosted = device.device_ip && device.host_ip === device.device_ip;
            rows.push({ label: 'Agent IP', value: `${device.host_ip}${selfHosted ? ' (self-hosted)' : ''}`, mono: true });
          }
          if (device.uart_device) rows.push({ label: 'UART device', value: device.uart_device, mono: true });
          if (device.usb_device) rows.push({ label: 'USB device', value: device.usb_device, mono: true });
          if (device.jtag_port > 0) rows.push({ label: 'JTAG port', value: String(device.jtag_port), mono: true });
          if (device.power_script) rows.push({ label: 'Power script', value: device.power_script, mono: true });
          if (device.sdmux_control) rows.push({ label: 'SDMux control', value: device.sdmux_control, mono: true });
          if (device.sdmux_sdcard) rows.push({ label: 'SD card path', value: device.sdmux_sdcard, mono: true });
          if (device.access_control_script) rows.push({ label: 'Access control', value: device.access_control_script, mono: true });
          if (device.version_script) rows.push({ label: 'Version script', value: device.version_script, mono: true });
          if (device.version_ref_file) rows.push({ label: 'Version ref file', value: device.version_ref_file, mono: true });
          if (device.version_script && device.version_poll_interval > 0) rows.push({ label: 'Version interval', value: `${device.version_poll_interval}s` });
          if (device.redeployment_script) rows.push({ label: 'Redeployment script', value: device.redeployment_script, mono: true });
          if (rows.length === 0) return null;
          return (
            <div className="bg-white rounded-xl border p-5 mb-4">
              <h2 className="text-sm font-semibold text-gray-700 mb-3">Parameters</h2>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
                {rows.map(({ label, value, mono }) => (
                  <React.Fragment key={label}>
                    <dt className="text-xs font-medium text-gray-400 whitespace-nowrap pt-0.5">{label}</dt>
                    <dd className={mono ? 'font-mono text-xs text-gray-700 break-all' : 'text-xs text-gray-700'}>{value}</dd>
                  </React.Fragment>
                ))}
              </dl>
            </div>
          );
        })()}

        {/* Redeploy — shown when redeployment_script is set but version_script is not (no version row) */}
        {device.redeployment_script && !device.version_script && device.active_booking?.username === me && (
          <div className="bg-white rounded-xl border p-5 mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-gray-700">Redeployment</p>
              <p className="text-xs text-gray-400 font-mono mt-0.5">{device.redeployment_script}</p>
            </div>
            <RedeployBtn />
          </div>
        )}

        {/* Redeploy result */}
        {(redeployMut.isError || redeployResult) && (
          <div className={`rounded-xl border p-5 mb-4 ${redeployResult?.ok ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
            <div className="flex items-center justify-between mb-2">
              <p className={`text-sm font-semibold ${redeployResult?.ok ? 'text-green-700' : 'text-red-700'}`}>
                {redeployResult?.ok ? '✓ Redeployment succeeded' : '✗ Redeployment failed'}
              </p>
              <button onClick={() => setRedeployResult(null)} className="text-gray-400 hover:text-gray-600"><X size={14} /></button>
            </div>
            {redeployResult?.stdout && (
              <pre className="text-xs font-mono bg-white/60 rounded p-2 max-h-48 overflow-y-auto whitespace-pre-wrap">{redeployResult.stdout}</pre>
            )}
            {redeployResult?.stderr && (
              <pre className="text-xs font-mono text-red-600 bg-white/60 rounded p-2 mt-1 max-h-24 overflow-y-auto whitespace-pre-wrap">{redeployResult.stderr}</pre>
            )}
            {redeployMut.isError && (
              <p className="text-xs text-red-600">{(redeployMut.error as Error).message}</p>
            )}
          </div>
        )}

      </div>

      {/* Edit device modal */}
      {showEdit && (
        <EditDeviceModal
          device={device}
          onClose={() => setShowEdit(false)}
          onSuccess={() => qc.invalidateQueries({ queryKey: ['device', id] })}
        />
      )}

      {/* Version detail modal */}
      {showVersionDetail && device.deployed_version && (() => {
        const vp = parseDeployedVersion(device.deployed_version);
        return (
          <div
            className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
            onClick={(e) => { if (e.target === e.currentTarget) setShowVersionDetail(false); }}
          >
            <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[80vh] overflow-y-auto p-6">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h2 className="text-lg font-bold text-gray-900">Version details</h2>
                  <p className="text-sm text-gray-500 font-mono mt-0.5">{device.name}</p>
                </div>
                <button onClick={() => setShowVersionDetail(false)} className="text-gray-400 hover:text-gray-600 mt-0.5">
                  <X size={18} />
                </button>
              </div>
              <div className="flex items-center gap-2 mb-4 pb-4 border-b">
                <span className={`text-sm font-semibold px-2 py-0.5 rounded ${vp.isClean ? 'bg-green-100 text-green-700' : vp.isClean === false ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'}`}>
                  {vp.isClean === true ? '✓ clean' : vp.isClean === false ? '✗ dirty' : 'version'}
                </span>
                <span className="font-mono text-xs text-gray-500">current: {vp.curSha}</span>
                {vp.refSha && (
                  <span className="font-mono text-xs text-gray-400">ref: {vp.refSha}</span>
                )}
              </div>
              <DiffContent isClean={vp.isClean} detail={vp.detail} />
            </div>
          </div>
        );
      })()}
    </div>
  );
}
