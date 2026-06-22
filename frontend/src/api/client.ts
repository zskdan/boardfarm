import axios from 'axios';
import type {
  ActivityEntry,
  AgentInfo,
  BookingInfo,
  CommandsInfo,
  DeviceCreate,
  DeviceInfo,
  SetupCreate,
  SetupInfo,
} from './types';

// ── localStorage keys ─────────────────────────────────────────────────────────

const LS_SERVER_URL    = 'bf_server_url';
const LS_DEFAULT_USER  = 'bf_username';
const LS_TOKEN         = 'bf_token';
const LS_BOOKING_LIMIT = 'bf_booking_limit';

// ── Server connection ─────────────────────────────────────────────────────────

export function getServerUrl(): string {
  return localStorage.getItem(LS_SERVER_URL) ?? 'http://localhost:8765';
}
export function setServerUrl(url: string) {
  localStorage.setItem(LS_SERVER_URL, url);
}

// ── Default user (pre-filled in all action forms; no mandatory login) ─────────

export function getDefaultUser(): string {
  return localStorage.getItem(LS_DEFAULT_USER) ?? '';
}
export function setDefaultUser(u: string) {
  localStorage.setItem(LS_DEFAULT_USER, u);
}
export const getUsername = getDefaultUser;
export const setUsername = setDefaultUser;

// ── Token ─────────────────────────────────────────────────────────────────────

export function getToken(): string {
  return localStorage.getItem(LS_TOKEN) ?? '';
}
export function setToken(t: string) {
  localStorage.setItem(LS_TOKEN, t);
}

// ── Booking limit ─────────────────────────────────────────────────────────────

export type BookingLimit = number | 'unlimited' | 'never';

export function getBookingLimit(): BookingLimit {
  const v = localStorage.getItem(LS_BOOKING_LIMIT);
  if (v === 'unlimited') return 'unlimited';
  if (v === 'never') return 'never';
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : 24;
}
export function setBookingLimit(v: BookingLimit) {
  localStorage.setItem(LS_BOOKING_LIMIT, String(v));
}

// ── Axios client factory ──────────────────────────────────────────────────────

function makeClient(user?: string) {
  const instance = axios.create({ baseURL: getServerUrl() });
  instance.interceptors.request.use((config) => {
    const token = getToken();
    const u = user ?? getDefaultUser();
    if (token) config.headers['X-Token'] = token;
    if (u) config.headers['X-User'] = u;
    return config;
  });
  return instance;
}

/** Read-only requests: use stored default user. */
function api() { return makeClient(); }
/** Mutating requests: caller provides the acting username. */
function apiAs(user: string) { return makeClient(user); }

// ── Health ────────────────────────────────────────────────────────────────────

export async function checkHealth(serverUrl: string): Promise<boolean> {
  try {
    const { data } = await axios.get(`${serverUrl}/health`, { timeout: 5000 });
    if (data.max_booking_hours !== undefined && !localStorage.getItem(LS_BOOKING_LIMIT)) {
      const mh = data.max_booking_hours;
      setBookingLimit(mh === null ? 'unlimited' : mh === 0 ? 'never' : (mh as number));
    }
    if (data.default_user && !getDefaultUser()) {
      setDefaultUser(data.default_user);
    }
    return true;
  } catch {
    return false;
  }
}

// ── Agents ────────────────────────────────────────────────────────────────────

export async function listAgents(): Promise<AgentInfo[]> {
  const { data } = await api().get<AgentInfo[]>('/agents');
  return data;
}

// ── Devices (Inventory) ───────────────────────────────────────────────────────

export async function listDevices(): Promise<DeviceInfo[]> {
  const { data } = await api().get<DeviceInfo[]>('/devices');
  return data;
}

export async function getDevice(id: string): Promise<DeviceInfo> {
  const { data } = await api().get<DeviceInfo>(`/devices/${id}`);
  return data;
}

export async function createDevice(body: DeviceCreate, username: string): Promise<DeviceInfo> {
  const { data } = await apiAs(username).post<DeviceInfo>('/devices', body);
  return data;
}

export async function updateDevice(
  id: string,
  body: Partial<DeviceCreate>,
  username: string,
): Promise<DeviceInfo> {
  const { data } = await apiAs(username).patch<DeviceInfo>(`/devices/${id}`, body);
  return data;
}

export async function deleteDevice(id: string, username: string): Promise<void> {
  await apiAs(username).delete(`/devices/${id}`);
}

export async function updateDeviceNotes(id: string, notes: string): Promise<DeviceInfo> {
  const { data } = await api().patch<DeviceInfo>(`/devices/${id}`, { current_notes: notes });
  return data;
}

// ── Bookings ──────────────────────────────────────────────────────────────────

export async function bookDevice(
  deviceId: string,
  durationHours: number,
  comment: string,
  username: string,
): Promise<BookingInfo> {
  const { data } = await apiAs(username).post<BookingInfo>(`/devices/${deviceId}/book`, {
    duration_hours: durationHours,
    comment,
  });
  return data;
}

export async function releaseBooking(bookingId: string, username: string): Promise<BookingInfo> {
  const { data } = await apiAs(username).delete<BookingInfo>(`/bookings/${bookingId}`);
  return data;
}

export async function extendBooking(bookingId: string, hours: number): Promise<BookingInfo> {
  const { data } = await api().patch<BookingInfo>(`/bookings/${bookingId}/extend`, { hours });
  return data;
}

export async function getCommands(bookingId: string): Promise<CommandsInfo> {
  const { data } = await api().get<CommandsInfo>(`/bookings/${bookingId}/commands`);
  return data;
}

export async function listBookings(params?: {
  device_id?: string;
  username?: string;
  active?: boolean;
  skip?: number;
  limit?: number;
}): Promise<BookingInfo[]> {
  const { data } = await api().get<BookingInfo[]>('/bookings', { params });
  return data;
}

export async function listSetups(): Promise<SetupInfo[]> {
  const { data } = await api().get<SetupInfo[]>('/setups');
  return data;
}

export async function createSetup(body: SetupCreate, username: string): Promise<SetupInfo> {
  const { data } = await apiAs(username).post<SetupInfo>('/setups', body);
  return data;
}

export async function updateSetup(id: string, body: Partial<SetupCreate>, username: string): Promise<SetupInfo> {
  const { data } = await apiAs(username).patch<SetupInfo>(`/setups/${id}`, body);
  return data;
}

export async function deleteSetup(id: string, username: string): Promise<void> {
  await apiAs(username).delete(`/setups/${id}`);
}

export async function bookSetup(id: string, durationHours: number, comment: string, username: string): Promise<BookingInfo[]> {
  const { data } = await apiAs(username).post<BookingInfo[]>(`/setups/${id}/book`, { duration_hours: durationHours, comment });
  return data;
}

export async function releaseSetupBooking(id: string, username: string): Promise<void> {
  await apiAs(username).delete(`/setups/${id}/booking`);
}

export async function listActivity(params?: {
  device_ref?: string;
  username?: string;
  action?: string;
  skip?: number;
  limit?: number;
}): Promise<ActivityEntry[]> {
  const { data } = await api().get<ActivityEntry[]>('/activity', { params });
  return data;
}

export async function getRedeployInfo(
  deviceId: string,
  username: string,
): Promise<{ exists: boolean; script_lines: number }> {
  const { data } = await apiAs(username).get(`/devices/${deviceId}/redeploy-info`);
  return data;
}

export async function redeployDevice(
  deviceId: string,
  username: string,
): Promise<{ ok: boolean; stdout: string; stderr: string; returncode: number }> {
  const { data } = await apiAs(username).post(`/devices/${deviceId}/redeploy`);
  return data;
}
