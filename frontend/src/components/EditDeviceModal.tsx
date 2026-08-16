import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createDevice, getDefaultUser, listDevices, setDefaultUser, updateDevice } from '../api/client';
import type { DeviceCreate, DeviceInfo } from '../api/types';

// ── Shared UI primitives ──────────────────────────────────────────────────────

export const inputCls =
  'border rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500';

export function Overlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      {children}
    </div>
  );
}

export function ModalCard({
  title, subtitle, onClose, wide, children,
}: {
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

export function Field({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-gray-600">{label}</span>
      {children}
    </label>
  );
}

export function ModalActions({
  onCancel, onConfirm, confirmLabel, confirmDisabled,
}: {
  onCancel: () => void; onConfirm: () => void; confirmLabel: string; confirmDisabled?: boolean;
}) {
  return (
    <div className="flex gap-2 justify-end mt-2">
      <button onClick={onCancel} className="px-4 py-2 text-sm border rounded-lg hover:bg-gray-50">
        Cancel
      </button>
      <button
        onClick={onConfirm}
        disabled={confirmDisabled}
        className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
      >
        {confirmLabel}
      </button>
    </div>
  );
}

// ── Clone-naming helpers ──────────────────────────────────────────────────────

// Bumps the trailing number in a string (preserving zero-padding width, e.g.
// "dev-01" -> "dev-02"), skipping any value already in `taken`. Strings with
// no trailing number get "-2", "-3", … appended (first clone is "-2" since
// the source is implicitly "-1").
function nextAvailableValue(base: string, taken: Set<string>): string {
  if (!base) return base;
  const m = base.match(/(\d+)$/);
  if (m) {
    const prefix = base.slice(0, -m[1].length);
    const width = m[1].length;
    let n = parseInt(m[1], 10) + 1;
    const pad = (x: number) => {
      const s = String(x);
      return m[1][0] === '0' && s.length <= width ? s.padStart(width, '0') : s;
    };
    let candidate = prefix + pad(n);
    while (taken.has(candidate)) { n++; candidate = prefix + pad(n); }
    return candidate;
  }
  let n = 2;
  let candidate = `${base}-${n}`;
  while (taken.has(candidate)) { n++; candidate = `${base}-${n}`; }
  return candidate;
}

function buildCloneForm(source: DeviceInfo, existingDevices: DeviceInfo[]): DeviceCreate {
  const others = existingDevices.filter((d) => d.id !== source.id);
  const names = new Set(others.map((d) => d.name));
  const ips = new Set(others.filter((d) => d.device_ip).map((d) => d.device_ip));
  return {
    name: nextAvailableValue(source.name, names),
    serial_number: source.serial_number,
    revision: source.revision,
    description: source.description,
    location: source.location,
    device_ip: source.device_ip ? nextAvailableValue(source.device_ip, ips) : '',
    host_ip: source.host_ip ?? '',
    features: source.features,
    jtag_port: source.jtag_port,
    ssh_user: source.ssh_user,
    ssh_port: source.ssh_port,
    power_script: source.power_script,
    power_args: source.power_args,
    usb_device: source.usb_device ?? '',
    uart_device: source.uart_device ?? '',
    sdmux_control: source.sdmux_control ?? '',
    sdmux_sdcard: source.sdmux_sdcard ?? '',
    access_control_script: source.access_control_script ?? '',
    enabled: source.enabled,
    current_notes: '', // notes are instance-specific — don't carry over
    version_script: source.version_script ?? '',
    version_ref_file: source.version_ref_file ?? '',
    version_poll_interval: source.version_poll_interval,
    redeployment_script: source.redeployment_script ?? '',
  };
}

// ── Add / Clone Device Modal ─────────────────────────────────────────────────

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

export function AddDeviceModal({ onClose, cloneFrom }: { onClose: () => void; cloneFrom?: DeviceInfo }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data: existingDevices = [] } = useQuery({ queryKey: ['devices'], queryFn: listDevices });
  const [username, setUsernameState] = useState(getDefaultUser());
  const [form, setForm] = useState<DeviceCreate>(() =>
    cloneFrom ? buildCloneForm(cloneFrom, existingDevices) : DEFAULT_DEVICE,
  );
  const [featuresRaw, setFeaturesRaw] = useState(() =>
    cloneFrom ? JSON.stringify(cloneFrom.features, null, 2) : '{}',
  );
  const [hasEthernet, setHasEthernet] = useState(() => !!(cloneFrom?.device_ip || cloneFrom?.ssh_port));
  const [hasSsh, setHasSsh] = useState(() => cloneFrom ? !!cloneFrom.ssh_port : true);
  const [hasAgent, setHasAgent] = useState(() => !!cloneFrom && !!(
    cloneFrom.host_ip || cloneFrom.jtag_port || cloneFrom.power_script || cloneFrom.usb_device ||
    cloneFrom.uart_device || cloneFrom.sdmux_control || cloneFrom.access_control_script || cloneFrom.version_script
  ));
  const [hasUsb, setHasUsb] = useState(() => !!cloneFrom?.usb_device);
  const [hasUart, setHasUart] = useState(() => !!cloneFrom?.uart_device);
  const [hasJtag, setHasJtag] = useState(() => !!cloneFrom?.jtag_port);
  const [hasPower, setHasPower] = useState(() => !!cloneFrom?.power_script);
  const [hasSdmux, setHasSdmux] = useState(() => !!cloneFrom?.sdmux_control);
  const [hasAccessControl, setHasAccessControl] = useState(() => !!cloneFrom?.access_control_script);
  const [hasVersion, setHasVersion] = useState(() => !!cloneFrom?.version_script);
  const [agentSelfHosted, setAgentSelfHosted] = useState(() =>
    !!(cloneFrom?.host_ip && cloneFrom?.device_ip && cloneFrom.host_ip === cloneFrom.device_ip),
  );

  // If the modal opened before the devices list was cached (e.g. from the
  // device detail page), re-derive the suggested name/IP once it arrives —
  // but only once, so it doesn't clobber anything the user has since typed.
  const appliedCloneDefaults = useRef(false);
  useEffect(() => {
    if (!cloneFrom || appliedCloneDefaults.current || existingDevices.length === 0) return;
    appliedCloneDefaults.current = true;
    const cloned = buildCloneForm(cloneFrom, existingDevices);
    setForm((f) => ({ ...f, name: cloned.name, device_ip: cloned.device_ip || f.device_ip }));
  }, [cloneFrom, existingDevices]);

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
      <ModalCard
        title={cloneFrom ? 'Clone Device' : 'Add Device'}
        subtitle={cloneFrom ? `Cloned from ${cloneFrom.name}` : undefined}
        onClose={onClose}
      >
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
                  onChange={(e) => {
                    setHasPower(e.target.checked);
                    if (e.target.checked && !form.power_script)
                      setForm(f => ({ ...f, power_script: '/opt/boardfarm/agent/scripts/power_control' }));
                  }} />
                Power Control
              </label>
              {hasPower && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-orange-100">
                  <Field label="Power Script *">
                    <input type="text" required className={`${inputCls} ${!form.power_script ? 'border-red-400 focus:ring-red-300' : ''}`}
                      value={form.power_script ?? ''}
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
            confirmLabel={mut.isPending ? 'Creating…' : cloneFrom ? 'Create clone' : 'Create'}
            confirmDisabled={mut.isPending || !form.name || !username
              || (hasEthernet && !form.device_ip?.trim())
              || (hasAgent && !agentSelfHosted && !form.host_ip?.trim())
              || (hasAgent && hasPower && !form.power_script?.trim())} />
        </div>
      </ModalCard>
    </Overlay>
  );
}

// ── Edit Device Modal ─────────────────────────────────────────────────────────

export function EditDeviceModal({
  device,
  onClose,
  onSuccess,
}: {
  device: DeviceInfo;
  onClose: () => void;
  onSuccess?: () => void;
}) {
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
  const [hasAgent, setHasAgent] = useState(
    !!(device.host_ip || device.jtag_port || device.power_script || device.usb_device ||
      device.uart_device || device.sdmux_control || device.access_control_script || device.version_script),
  );
  const [hasUsb, setHasUsb] = useState(!!device.usb_device);
  const [hasUart, setHasUart] = useState(!!device.uart_device);
  const [hasJtag, setHasJtag] = useState(!!device.jtag_port);
  const [hasPower, setHasPower] = useState(!!device.power_script);
  const [hasSdmux, setHasSdmux] = useState(!!device.sdmux_control);
  const [hasAccessControl, setHasAccessControl] = useState(!!device.access_control_script);
  const [hasVersion, setHasVersion] = useState(!!device.version_script);
  const [agentSelfHosted, setAgentSelfHosted] = useState(
    !!(device.host_ip && device.device_ip && device.host_ip === device.device_ip),
  );

  const updateMut = useMutation({
    mutationFn: () => {
      const baseFeatures: Record<string, unknown> = (() => {
        try { return JSON.parse(featuresRaw); } catch { return device.features; }
      })();
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
    onSuccess: () => {
      setDefaultUser(username);
      qc.invalidateQueries({ queryKey: ['devices'] });
      onSuccess?.();
      onClose();
    },
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
            <span className="font-mono text-sm text-gray-500 bg-gray-50 border rounded-lg px-3 py-1.5">
              {device.device_id || '—'}
            </span>
          </Field>
          {([
            ['Name', 'name'],
            ['Serial Number', 'serial_number'],
            ['Revision', 'revision'],
            ['Description', 'description'],
            ['Location', 'location'],
          ] as [string, keyof typeof form][]).map(([label, key]) => (
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
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-blue-400" checked={agentSelfHosted}
                  onChange={(e) => setAgentSelfHosted(e.target.checked)} />
                Self hosted (agent runs on the device itself)
              </label>
              {agentSelfHosted ? (
                <p className="text-xs text-gray-400 pl-1">
                  Agent IP will use the device IP
                  {form.device_ip?.trim() ? ` (${form.device_ip})` : ' — set device IP above'}
                </p>
              ) : (
                <Field label={<>Hardware agent IP <span className="text-red-500">*</span></>}>
                  <input type="text"
                    className={`${inputCls} ${!form.host_ip?.trim() ? 'border-red-300 focus:ring-red-400' : ''}`}
                    value={form.host_ip ?? ''}
                    onChange={(e) => setForm(f => ({ ...f, host_ip: e.target.value }))}
                    placeholder="Required" />
                </Field>
              )}
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
              <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
                <input type="checkbox" className="accent-orange-500" checked={hasPower}
                  onChange={(e) => {
                    setHasPower(e.target.checked);
                    if (e.target.checked && !form.power_script)
                      setForm(f => ({ ...f, power_script: '/opt/boardfarm/agent/scripts/power_control' }));
                  }} />
                Power Control
              </label>
              {hasPower && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-orange-100">
                  <Field label="Power Script *">
                    <input type="text" required className={`${inputCls} ${!form.power_script ? 'border-red-400 focus:ring-red-300' : ''}`}
                      value={form.power_script ?? ''}
                      onChange={(e) => setForm(f => ({ ...f, power_script: e.target.value }))} />
                  </Field>
                  <Field label="Power Script Args (JSON)">
                    <textarea className={`${inputCls} font-mono`} rows={2}
                      value={JSON.stringify(form.power_args ?? {})}
                      onChange={(e) => {
                        try { setForm(f => ({ ...f, power_args: JSON.parse(e.target.value) })); }
                        catch { /* ignore */ }
                      }} />
                  </Field>
                </div>
              )}
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
                    <input type="number" min={1} className={inputCls}
                      value={form.version_poll_interval ?? 30}
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

          {updateMut.error && (
            <p className="text-xs text-red-600">{(updateMut.error as Error).message}</p>
          )}
          <ModalActions
            onCancel={onClose}
            onConfirm={() => updateMut.mutate()}
            confirmLabel={updateMut.isPending ? 'Saving…' : 'Save changes'}
            confirmDisabled={
              updateMut.isPending || !form.name || !username ||
              (hasEthernet && !form.device_ip?.trim()) ||
              (hasAgent && !agentSelfHosted && !form.host_ip?.trim()) ||
              (hasAgent && hasPower && !form.power_script?.trim())
            }
          />
        </div>
      </ModalCard>
    </Overlay>
  );
}
