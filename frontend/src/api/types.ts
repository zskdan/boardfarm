export interface AgentInfo {
  id?: string;
  name: string;
  url: string;
  last_seen?: string;
  online: boolean;
  board_count?: number;
  self?: boolean;
}

export interface ToolInfo {
  id: string;
  board_id: string;
  type: string;
  model: string;
  connection: string;
  connection_detail: string;
  notes: string;
}

export interface ToolCreate {
  type: string;
  model: string;
  connection: string;
  connection_detail: string;
  notes: string;
}

export interface BookingInfo {
  id: string;
  board_id: string;
  board_name: string;
  username: string;
  start_time: string;
  end_time: string;
  extended: boolean;
  active: boolean;
  release_reason: string;
  comment: string;
}

export interface BoardInfo {
  id: string;
  device_id: string;
  serial_number: string;
  revision: string;
  name: string;
  description: string;
  location: string;
  agent_id: string | null;
  host_ip: string | null;
  features: Record<string, unknown>;
  jtag_port: number;
  uart_tcp_port: number;
  ssh_user: string;
  ssh_port: number;
  power_script: string;
  power_args: Record<string, unknown>;
  enabled: boolean;
  agent_online: boolean;
  active_booking: BookingInfo | null;
  tools: ToolInfo[];
  current_notes: string;
}

export interface BoardCreate {
  name: string;
  serial_number: string;
  revision: string;
  description: string;
  location: string;
  host_ip?: string | null;
  features: Record<string, unknown>;
  jtag_port: number;
  uart_tcp_port: number;
  ssh_user: string;
  ssh_port: number;
  power_script: string;
  power_args: Record<string, unknown>;
  enabled: boolean;
  current_notes: string;
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
  board_id: string | null;
  board_name: string;
  detail: string;
}
