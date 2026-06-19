export interface AgentInfo {
  id?: string;
  name: string;
  url: string;
  last_seen?: string;
  online: boolean;
  device_count?: number;
  self?: boolean;
}

export interface BookingInfo {
  id: string;
  device_id: string;
  device_name: string;
  username: string;
  start_time: string;
  end_time: string;
  extended: boolean;
  active: boolean;
  release_reason: string;
  comment: string;
  setup_id: string | null;
  setup_name: string;
}

export interface SetupDeviceInfo {
  id: string;
  name: string;
  device_id: string;
  location: string;
  agent_online: boolean;
  deployed_version: string;
  active_booking_username: string | null;
  active_booking_setup_name: string | null;
}

export interface SetupBookingInfo {
  username: string;
  start_time: string;
  end_time: string;
}

export interface SetupInfo {
  id: string;
  name: string;
  description: string;
  created_at: string;
  devices: SetupDeviceInfo[];
  all_available: boolean;
  active_booking: SetupBookingInfo | null;
}

export interface SetupCreate {
  name: string;
  description: string;
  device_ids: string[];
}

export interface DeviceInfo {
  id: string;
  device_id: string;
  serial_number: string;
  revision: string;
  name: string;
  description: string;
  location: string;
  device_ip: string;
  agent_id: string | null;
  host_ip: string | null;
  features: Record<string, unknown>;
  jtag_port: number;
  ssh_user: string;
  ssh_port: number;
  power_script: string;
  power_args: Record<string, unknown>;
  usb_device: string;
  uart_device: string;
  sdmux_control: string;
  sdmux_sdcard: string;
  access_control_script: string;
  enabled: boolean;
  agent_online: boolean;
  deployed_version: string;
  active_booking: BookingInfo | null;
  current_notes: string;
  version_script: string;
  version_poll_interval: number;
  redeployment_script: string;
}


export interface DeviceCreate {
  name: string;
  serial_number: string;
  revision: string;
  description: string;
  location: string;
  device_ip?: string;
  host_ip?: string | null;
  features: Record<string, unknown>;
  jtag_port: number;
  ssh_user: string;
  ssh_port: number;
  power_script: string;
  power_args: Record<string, unknown>;
  usb_device?: string;
  uart_device?: string;
  sdmux_control?: string;
  sdmux_sdcard?: string;
  access_control_script?: string;
  enabled: boolean;
  current_notes: string;
  version_script?: string;
  version_poll_interval?: number;
  redeployment_script?: string;
}


export interface CommandsInfo {
  jtag_connect: string;
  vivado_tcl: string;
  uart: string;
  ssh: string;
  power_on: string;
}

export interface ActivityEntry {
  id: string;
  timestamp: string;
  action: string;
  username: string;
  device_ref: string | null;
  device_name: string;
  device_id: string;
  detail: string;
}
