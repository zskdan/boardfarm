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
  bookDevice,
  createDevice,
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
  updateDevice,
  getLocalAppName,
  setLocalAppName,
} from '../api/client';
import type { BookingLimit } from '../api/client';
import type { DeviceCreate, DeviceInfo } from '../api/types';
import StatusBadge from '../components/StatusBadge';
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

const FIELD_BASIC: [string, keyof DeviceCreate][] = [
  ['Name', 'name'],
  ['Serial Number', 'serial_number'],
  ['Revision', 'revision'],
  ['Description', 'description'],
  ['Location', 'location'],
];

const DEFAULT_DEVICE: DeviceCreate = {
  name: '', serial_number: '', revision: '', description: '',
  location: '', device_ip: '', host_ip: '', features: {}, jtag_port: 3121,
  ssh_user: 'root', ssh_port: 22, power_script: '', power_args: {},
  usb_device: '', uart_device: '', sdmux_control: '/dev/sg0', sdmux_sdcard: '', access_control_script: '',
  version_script: '/opt/sca/get-version.sh', version_ref_file: '/opt/sca/ref-version.txt', version_poll_interval: 30, redeployment_script: '', enabled: true, current_notes: '',
};

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
// Add Device Modal
// ─────────────────────────────────────────────────────────────────────────────

function AddDeviceModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [username, setUsernameState] = useState(getDefaultUser());
  const [form, setForm] = useState<DeviceCreate>(DEFAULT_DEVICE);
  const [featuresRaw, setFeaturesRaw] = useState('{}');
  const [hasEthernet, setHasEthernet] = useState(false);
  const [hasSsh, setHasSsh] = useState(true);
  const [hasAgent, setHasAgent] = useState(false);
  const [hasUsb, setHasUsb] = useState(false);
  const [hasUart, setHasUart] = useState(false);
  const [hasJtag, setHasJtag] = useState(false);
  const [hasPower, setHasPower] = useState(false);
  const [hasSdmux, setHasSdmux] = useState(false);
  const [hasAccessControl, setHasAccessControl] = useState(false);
  const [hasVersion, setHasVersion] = useState(false);
  const [agentSelfHosted, setAgentSelfHosted] = useState(false);

  const mut = useMutation({
    mutationFn: () => {
      const baseFeatures: Record<string, unknown> = (() => { try { return JSON.parse(featuresRaw); } catch { return {}; } })();
      if (hasAgent && hasJtag) baseFeatures.jtag = true; else delete baseFeatures.jtag;
      if (hasAgent && hasUart) baseFeatures.uart = true; else delete baseFeatures.uart;
      if (hasAgent && hasUsb) baseFeatures.usb = true; else delete baseFeatures.usb;
      if (hasAgent && hasPower) baseFeatures.power_ctrl = true; else delete baseFeatures.power_ctrl;
      if (hasAgent && hasSdmux) baseFeatures.sdmux = true; else delete baseFeatures.sdmux;
      if (hasAgent && hasAccessControl) baseFeatures.session_ctrl = true; else delete baseFeatures.session_ctrl;
      if (hasAgent && hasVersion) baseFeatures.version_ctrl = true; else delete baseFeatures.version_ctrl;
      const payload: DeviceCreate = {
        ...form,
        features: baseFeatures,
        device_ip: hasEthernet ? form.device_ip ?? '' : '',
        ssh_user: hasEthernet && hasSsh ? form.ssh_user : 'root',
        ssh_port: hasEthernet && hasSsh ? form.ssh_port : 0,
        host_ip: hasAgent ? (agentSelfHosted ? form.device_ip ?? '' : form.host_ip ?? '') : '',
        jtag_port: hasAgent && hasJtag ? form.jtag_port : 0,
        power_script: hasAgent && hasPower ? form.power_script : '',
        power_args: hasAgent && hasPower ? form.power_args : {},
        usb_device: hasAgent && hasUsb ? form.usb_device ?? '' : '',
        uart_device: hasAgent && hasUart ? form.uart_device ?? '' : '',
        sdmux_control: hasAgent && hasSdmux ? form.sdmux_control ?? '' : '',
        sdmux_sdcard: hasAgent && hasSdmux ? form.sdmux_sdcard ?? '' : '',
        access_control_script: hasAgent && hasAccessControl ? form.access_control_script ?? '' : '',
        version_script: hasAgent && hasVersion ? form.version_script ?? '' : '',
        version_ref_file: hasAgent && hasVersion ? form.version_ref_file ?? '' : '',
        version_poll_interval: hasAgent && hasVersion ? form.version_poll_interval ?? 30 : 0,
        redeployment_script: hasAgent && hasVersion ? form.redeployment_script ?? '' : '',
      };
      return createDevice(payload, username);
    },
    onSuccess: (device) => {
      setDefaultUser(username);
      qc.invalidateQueries({ queryKey: ['devices'] });
      onClose();
      navigate(`/devices/${device.id}`);
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

          {/* Ethernet section */}
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700 border-t pt-3">
            <input type="checkbox" className="accent-blue-600" checked={hasEthernet}
              onChange={(e) => setHasEthernet(e.target.checked)} />
            Ethernet
          </label>
          {hasEthernet && (
            <div className="flex flex-col gap-3 pl-3 border-l-2 border-green-200">
              <Field label={<>Device IP <span className="text-red-500">*</span></>}>
                <input type="text"
                  className={`${inputCls} ${!form.device_ip?.trim() ? 'border-red-300 focus:ring-red-400' : ''}`}
                  value={form.device_ip ?? ''}
                  placeholder="Required"
                  onChange={(e) => setForm(f => ({ ...f, device_ip: e.target.value }))} />
              </Field>
              {/* SSH sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-green-600" checked={hasSsh}
                  onChange={(e) => setHasSsh(e.target.checked)} />
                SSH
              </label>
              {hasSsh && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-green-100">
                  <Field label="SSH User">
                    <input type="text" className={inputCls} value={form.ssh_user}
                      onChange={(e) => setForm(f => ({ ...f, ssh_user: e.target.value }))} />
                  </Field>
                  <Field label="SSH Port">
                    <input type="number" className={inputCls} value={form.ssh_port}
                      onChange={(e) => setForm(f => ({ ...f, ssh_port: Number(e.target.value) }))} />
                  </Field>
                </div>
              )}
            </div>
          )}

          {/* Agent section */}
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700 border-t pt-3">
            <input type="checkbox" className="accent-blue-600" checked={hasAgent}
              onChange={(e) => setHasAgent(e.target.checked)} />
            Hardware agent
          </label>
          {hasAgent && (
            <div className="flex flex-col gap-3 pl-3 border-l-2 border-blue-200">
              {/* Self hosted sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-blue-400" checked={agentSelfHosted}
                  onChange={(e) => setAgentSelfHosted(e.target.checked)} />
                Self hosted (agent runs on the device itself)
              </label>
              {agentSelfHosted ? (
                <p className="text-xs text-gray-400 pl-1">
                  Agent IP will use the device IP{form.device_ip?.trim() ? ` (${form.device_ip})` : ' — set device IP above'}
                </p>
              ) : (
                <Field label={<>Hardware agent IP <span className="text-red-500">*</span></>}>
                  <input type="text" className={`${inputCls} ${!form.host_ip?.trim() ? 'border-red-300 focus:ring-red-400' : ''}`}
                    value={form.host_ip ?? ''}
                    onChange={(e) => setForm(f => ({ ...f, host_ip: e.target.value }))}
                    placeholder="Required" />
                </Field>
              )}
              {/* USB sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-purple-600" checked={hasUsb}
                  onChange={(e) => setHasUsb(e.target.checked)} />
                USB
              </label>
              {hasUsb && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-purple-100">
                  <Field label="USB device">
                    <input type="text" className={`${inputCls} font-mono`}
                      placeholder="ex: /dev/bus/usb/001/002"
                      value={form.usb_device ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, usb_device: e.target.value }))} />
                  </Field>
                </div>
              )}
              {/* UART sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-purple-500" checked={hasUart}
                  onChange={(e) => setHasUart(e.target.checked)} />
                UART
              </label>
              {hasUart && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-purple-100">
                  <Field label="UART device">
                    <input type="text" className={`${inputCls} font-mono`}
                      placeholder="ex: /dev/ttyUSB0"
                      value={form.uart_device ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, uart_device: e.target.value }))} />
                  </Field>
                </div>
              )}
              {/* JTAG sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-blue-500" checked={hasJtag}
                  onChange={(e) => setHasJtag(e.target.checked)} />
                JTAG
              </label>
              {hasJtag && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-blue-100">
                  <Field label="JTAG Port">
                    <input type="number" className={inputCls} value={form.jtag_port}
                      onChange={(e) => setForm(f => ({ ...f, jtag_port: Number(e.target.value) }))} />
                  </Field>
                </div>
              )}
              {/* SDMux sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-teal-500" checked={hasSdmux}
                  onChange={(e) => {
                    setHasSdmux(e.target.checked);
                    if (e.target.checked && !form.sdmux_control?.trim())
                      setForm(f => ({ ...f, sdmux_control: '/dev/sg0' }));
                  }} />
                SDMux
              </label>
              {hasSdmux && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-teal-100">
                  <Field label="SDMux control device">
                    <input type="text" className={`${inputCls} font-mono`}
                      placeholder="ex: /dev/sg0"
                      value={form.sdmux_control ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, sdmux_control: e.target.value }))} />
                  </Field>
                  <Field label="SD card path">
                    <input type="text" className={`${inputCls} font-mono`}
                      placeholder="ex: /dev/disk/by-path/..."
                      value={form.sdmux_sdcard ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, sdmux_sdcard: e.target.value }))} />
                  </Field>
                </div>
              )}
              {/* Power Control sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-orange-500" checked={hasPower}
                  onChange={(e) => setHasPower(e.target.checked)} />
                Power Control
              </label>
              {hasPower && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-orange-100">
                  <Field label="Power Script">
                    <input type="text" className={inputCls} value={form.power_script ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, power_script: e.target.value }))} />
                  </Field>
                  <Field label="Power Script Args (JSON)">
                    <textarea className={`${inputCls} font-mono`} rows={2}
                      value={JSON.stringify(form.power_args ?? {})}
                      onChange={(e) => { try { setForm(f => ({ ...f, power_args: JSON.parse(e.target.value) })); } catch { /* ignore */ } }} />
                  </Field>
                </div>
              )}
              {/* Access Control sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-rose-500" checked={hasAccessControl}
                  onChange={(e) => setHasAccessControl(e.target.checked)} />
                Access Control
              </label>
              {hasAccessControl && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-rose-100">
                  <Field label="Access control script">
                    <input type="text" className={`${inputCls} font-mono`}
                      placeholder="/opt/boardfarm/agent/scripts/access-control"
                      value={form.access_control_script ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, access_control_script: e.target.value }))} />
                  </Field>
                </div>
              )}
              {/* Version Control sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-violet-500" checked={hasVersion}
                  onChange={(e) => setHasVersion(e.target.checked)} />
                Version Control
              </label>
              {hasVersion && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-violet-100">
                  <Field label="Get Version Script Path">
                    <input type="text" className={`${inputCls} font-mono`}
                      placeholder="/opt/sca/get-version.sh"
                      value={form.version_script ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, version_script: e.target.value }))} />
                  </Field>
                  <Field label="Reference Version File Path">
                    <input type="text" className={`${inputCls} font-mono`}
                      placeholder="/opt/sca/ref-version.txt"
                      value={form.version_ref_file ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, version_ref_file: e.target.value }))} />
                  </Field>
                  <Field label="Check interval (seconds)">
                    <input type="number" min={1} className={inputCls} value={form.version_poll_interval ?? 30}
                      onChange={(e) => setForm(f => ({ ...f, version_poll_interval: Number(e.target.value) }))} />
                  </Field>
                  <Field label="Redeployment script path">
                    <input type="text" className={`${inputCls} font-mono`}
                      placeholder="ex: /opt/scripts/redeploy.sh"
                      value={form.redeployment_script ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, redeployment_script: e.target.value }))} />
                  </Field>
                </div>
              )}
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
            confirmDisabled={mut.isPending || !form.name || !username
              || (hasEthernet && !form.device_ip?.trim())
              || (hasAgent && !agentSelfHosted && !form.host_ip?.trim())} />
        </div>
      </ModalCard>
    </Overlay>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Edit Device Modal
// ─────────────────────────────────────────────────────────────────────────────

function EditDeviceModal({ device, onClose }: { device: DeviceInfo; onClose: () => void }) {
  const qc = useQueryClient();
  const [username, setUsernameState] = useState(getDefaultUser());
  const [form, setForm] = useState({
    name: device.name,
    serial_number: device.serial_number,
    revision: device.revision,
    description: device.description,
    location: device.location,
    device_ip: device.device_ip ?? '',
    host_ip: device.host_ip ?? '',
    current_notes: device.current_notes,
    ssh_user: device.ssh_user,
    ssh_port: device.ssh_port,
    jtag_port: device.jtag_port,
    power_script: device.power_script,
    power_args: device.power_args,
    usb_device: device.usb_device ?? '',
    uart_device: device.uart_device ?? '',
    sdmux_control: device.sdmux_control ?? '',
    sdmux_sdcard: device.sdmux_sdcard ?? '',
    access_control_script: device.access_control_script ?? '',
    version_script: device.version_script ?? '',
    version_ref_file: device.version_ref_file ?? '',
    version_poll_interval: device.version_poll_interval ?? 30,
    redeployment_script: device.redeployment_script ?? '',
    enabled: device.enabled,
  });
  const [featuresRaw, setFeaturesRaw] = useState(JSON.stringify(device.features, null, 2));
  const [hasEthernet, setHasEthernet] = useState(!!(device.device_ip || device.ssh_port));
  const [hasSsh, setHasSsh] = useState(!!device.ssh_port);
  const [hasAgent, setHasAgent] = useState(!!(device.host_ip || device.jtag_port || device.power_script || device.usb_device || device.uart_device || device.sdmux_control || device.access_control_script || device.version_script));
  const [hasUsb, setHasUsb] = useState(!!device.usb_device);
  const [hasUart, setHasUart] = useState(!!device.uart_device);
  const [hasJtag, setHasJtag] = useState(!!device.jtag_port);
  const [hasPower, setHasPower] = useState(!!device.power_script);
  const [hasSdmux, setHasSdmux] = useState(!!device.sdmux_control);
  const [hasAccessControl, setHasAccessControl] = useState(!!device.access_control_script);
  const [hasVersion, setHasVersion] = useState(!!device.version_script);
  const [agentSelfHosted, setAgentSelfHosted] = useState(
    !!(device.host_ip && device.device_ip && device.host_ip === device.device_ip)
  );

  const updateMut = useMutation({
    mutationFn: () => {
      const baseFeatures: Record<string, unknown> = (() => { try { return JSON.parse(featuresRaw); } catch { return device.features; } })();
      if (hasAgent && hasJtag) baseFeatures.jtag = true; else delete baseFeatures.jtag;
      if (hasAgent && hasUart) baseFeatures.uart = true; else delete baseFeatures.uart;
      if (hasAgent && hasUsb) baseFeatures.usb = true; else delete baseFeatures.usb;
      if (hasAgent && hasPower) baseFeatures.power_ctrl = true; else delete baseFeatures.power_ctrl;
      if (hasAgent && hasSdmux) baseFeatures.sdmux = true; else delete baseFeatures.sdmux;
      if (hasAgent && hasAccessControl) baseFeatures.session_ctrl = true; else delete baseFeatures.session_ctrl;
      if (hasAgent && hasVersion) baseFeatures.version_ctrl = true; else delete baseFeatures.version_ctrl;
      return updateDevice(device.id, {
        ...form,
        features: baseFeatures,
        device_ip: hasEthernet ? form.device_ip : '',
        ssh_user: hasEthernet && hasSsh ? form.ssh_user : 'root',
        ssh_port: hasEthernet && hasSsh ? form.ssh_port : 0,
        host_ip: hasAgent ? (agentSelfHosted ? form.device_ip : form.host_ip) : '',
        jtag_port: hasAgent && hasJtag ? form.jtag_port : 0,
        power_script: hasAgent && hasPower ? form.power_script : '',
        power_args: hasAgent && hasPower ? form.power_args : {},
        usb_device: hasAgent && hasUsb ? form.usb_device : '',
        uart_device: hasAgent && hasUart ? form.uart_device : '',
        sdmux_control: hasAgent && hasSdmux ? form.sdmux_control : '',
        sdmux_sdcard: hasAgent && hasSdmux ? form.sdmux_sdcard : '',
        access_control_script: hasAgent && hasAccessControl ? form.access_control_script : '',
        version_script: hasAgent && hasVersion ? form.version_script : '',
        version_ref_file: hasAgent && hasVersion ? form.version_ref_file : '',
        version_poll_interval: hasAgent && hasVersion ? form.version_poll_interval : 0,
        redeployment_script: hasAgent && hasVersion ? form.redeployment_script : '',
      }, username);
    },
    onSuccess: () => { setDefaultUser(username); qc.invalidateQueries({ queryKey: ['devices'] }); onClose(); },
  });

  return (
    <Overlay onClose={onClose}>
      <ModalCard title={`Edit — ${device.name}`} onClose={onClose} wide>
        <div className="flex flex-col gap-3">
          <Field label="Your username">
            <input className={inputCls} value={username}
              onChange={(e) => setUsernameState(e.target.value)} placeholder="Required" />
          </Field>
          <Field label="Device ID">
            <span className="font-mono text-sm text-gray-500 bg-gray-50 border rounded-lg px-3 py-1.5">{device.device_id || '—'}</span>
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

          {/* Ethernet section */}
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700 border-t pt-3">
            <input type="checkbox" className="accent-blue-600" checked={hasEthernet}
              onChange={(e) => setHasEthernet(e.target.checked)} />
            Ethernet
          </label>
          {hasEthernet && (
            <div className="flex flex-col gap-3 pl-3 border-l-2 border-green-200">
              <Field label={<>Device IP <span className="text-red-500">*</span></>}>
                <input type="text"
                  className={`${inputCls} ${!form.device_ip?.trim() ? 'border-red-300 focus:ring-red-400' : ''}`}
                  value={form.device_ip ?? ''}
                  placeholder="Required"
                  onChange={(e) => setForm(f => ({ ...f, device_ip: e.target.value }))} />
              </Field>
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-green-600" checked={hasSsh}
                  onChange={(e) => setHasSsh(e.target.checked)} />
                SSH
              </label>
              {hasSsh && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-green-100">
                  <Field label="SSH User">
                    <input type="text" className={inputCls} value={form.ssh_user ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, ssh_user: e.target.value }))} />
                  </Field>
                  <Field label="SSH Port">
                    <input type="number" className={inputCls} value={Number(form.ssh_port)}
                      onChange={(e) => setForm(f => ({ ...f, ssh_port: Number(e.target.value) }))} />
                  </Field>
                </div>
              )}
            </div>
          )}

          {/* Agent section */}
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700 border-t pt-3">
            <input type="checkbox" className="accent-blue-600" checked={hasAgent}
              onChange={(e) => setHasAgent(e.target.checked)} />
            Hardware agent
          </label>
          {hasAgent && (
            <div className="flex flex-col gap-3 pl-3 border-l-2 border-blue-200">
              {/* Self hosted sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-blue-400" checked={agentSelfHosted}
                  onChange={(e) => setAgentSelfHosted(e.target.checked)} />
                Self hosted (agent runs on the device itself)
              </label>
              {agentSelfHosted ? (
                <p className="text-xs text-gray-400 pl-1">
                  Agent IP will use the device IP{form.device_ip?.trim() ? ` (${form.device_ip})` : ' — set device IP above'}
                </p>
              ) : (
                <Field label={<>Hardware agent IP <span className="text-red-500">*</span></>}>
                  <input type="text" className={`${inputCls} ${!form.host_ip?.trim() ? 'border-red-300 focus:ring-red-400' : ''}`}
                    value={form.host_ip ?? ''}
                    onChange={(e) => setForm(f => ({ ...f, host_ip: e.target.value }))}
                    placeholder="Required" />
                </Field>
              )}
              {/* USB sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-purple-600" checked={hasUsb}
                  onChange={(e) => setHasUsb(e.target.checked)} />
                USB
              </label>
              {hasUsb && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-purple-100">
                  <Field label="USB device">
                    <input type="text" className={`${inputCls} font-mono`}
                      placeholder="ex: /dev/bus/usb/001/002"
                      value={form.usb_device}
                      onChange={(e) => setForm(f => ({ ...f, usb_device: e.target.value }))} />
                  </Field>
                </div>
              )}
              {/* UART sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-purple-500" checked={hasUart}
                  onChange={(e) => setHasUart(e.target.checked)} />
                UART
              </label>
              {hasUart && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-purple-100">
                  <Field label="UART device">
                    <input type="text" className={`${inputCls} font-mono`}
                      placeholder="ex: /dev/ttyUSB0"
                      value={form.uart_device}
                      onChange={(e) => setForm(f => ({ ...f, uart_device: e.target.value }))} />
                  </Field>
                </div>
              )}
              {/* JTAG sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-blue-500" checked={hasJtag}
                  onChange={(e) => setHasJtag(e.target.checked)} />
                JTAG
              </label>
              {hasJtag && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-blue-100">
                  <Field label="JTAG Port">
                    <input type="number" className={inputCls} value={Number(form.jtag_port)}
                      onChange={(e) => setForm(f => ({ ...f, jtag_port: Number(e.target.value) }))} />
                  </Field>
                </div>
              )}
              {/* SDMux sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-teal-500" checked={hasSdmux}
                  onChange={(e) => {
                    setHasSdmux(e.target.checked);
                    if (e.target.checked && !form.sdmux_control?.trim())
                      setForm(f => ({ ...f, sdmux_control: '/dev/sg0' }));
                  }} />
                SDMux
              </label>
              {hasSdmux && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-teal-100">
                  <Field label="SDMux control device">
                    <input type="text" className={`${inputCls} font-mono`}
                      placeholder="ex: /dev/sg0"
                      value={form.sdmux_control ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, sdmux_control: e.target.value }))} />
                  </Field>
                  <Field label="SD card path">
                    <input type="text" className={`${inputCls} font-mono`}
                      placeholder="ex: /dev/disk/by-path/..."
                      value={form.sdmux_sdcard ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, sdmux_sdcard: e.target.value }))} />
                  </Field>
                </div>
              )}
              {/* Power Control sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-orange-500" checked={hasPower}
                  onChange={(e) => setHasPower(e.target.checked)} />
                Power Control
              </label>
              {hasPower && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-orange-100">
                  <Field label="Power Script">
                    <input type="text" className={inputCls} value={form.power_script ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, power_script: e.target.value }))} />
                  </Field>
                  <Field label="Power Script Args (JSON)">
                    <textarea className={`${inputCls} font-mono`} rows={2}
                      value={JSON.stringify(form.power_args ?? {})}
                      onChange={(e) => { try { setForm(f => ({ ...f, power_args: JSON.parse(e.target.value) })); } catch { /* ignore */ } }} />
                  </Field>
                </div>
              )}
              {/* Access Control sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-rose-500" checked={hasAccessControl}
                  onChange={(e) => setHasAccessControl(e.target.checked)} />
                Access Control
              </label>
              {hasAccessControl && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-rose-100">
                  <Field label="Access control script">
                    <input type="text" className={`${inputCls} font-mono`}
                      placeholder="/opt/boardfarm/agent/scripts/access-control"
                      value={form.access_control_script ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, access_control_script: e.target.value }))} />
                  </Field>
                </div>
              )}
              {/* Version Control sub-checkbox */}
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-violet-500" checked={hasVersion}
                  onChange={(e) => setHasVersion(e.target.checked)} />
                Version Control
              </label>
              {hasVersion && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-violet-100">
                  <Field label="Get Version Script Path">
                    <input type="text" className={`${inputCls} font-mono`}
                      placeholder="/opt/sca/get-version.sh"
                      value={form.version_script ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, version_script: e.target.value }))} />
                  </Field>
                  <Field label="Reference Version File Path">
                    <input type="text" className={`${inputCls} font-mono`}
                      placeholder="/opt/sca/ref-version.txt"
                      value={form.version_ref_file ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, version_ref_file: e.target.value }))} />
                  </Field>
                  <Field label="Check interval (seconds)">
                    <input type="number" min={1} className={inputCls} value={form.version_poll_interval ?? 30}
                      onChange={(e) => setForm(f => ({ ...f, version_poll_interval: Number(e.target.value) }))} />
                  </Field>
                  <Field label="Redeployment script path">
                    <input type="text" className={`${inputCls} font-mono`}
                      placeholder="ex: /opt/scripts/redeploy.sh"
                      value={form.redeployment_script ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, redeployment_script: e.target.value }))} />
                  </Field>
                </div>
              )}
            </div>
          )}

          <label className="flex items-center gap-2 text-sm border-t pt-3">
            <input type="checkbox" checked={form.enabled}
              onChange={(e) => setForm(f => ({ ...f, enabled: e.target.checked }))} />
            Enabled
          </label>

          {updateMut.error && <p className="text-xs text-red-600">{(updateMut.error as Error).message}</p>}
          <ModalActions onCancel={onClose} onConfirm={() => updateMut.mutate()}
            confirmLabel={updateMut.isPending ? 'Saving…' : 'Save changes'}
            confirmDisabled={updateMut.isPending || !form.name || !username
              || (hasEthernet && !form.device_ip?.trim())
              || (hasAgent && !agentSelfHosted && !form.host_ip?.trim())} />
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
  const [editDevice, setEditDevice] = useState<DeviceInfo | null>(null);
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
      {bookDevice2          && <BookModal device={bookDevice2} onClose={() => setBookDevice2(null)} />}
      {releaseDevice        && <ReleaseModal device={releaseDevice} onClose={() => setReleaseDevice(null)} />}
    </div>
  );
}
