import axios from 'axios';
import type {
  ActivityEntry,
  AgentInfo,
  BoardCreate,
  BoardInfo,
  BookingInfo,
  CommandsInfo,
  ToolCreate,
  ToolInfo,
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
// Backward-compat aliases used by other pages
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
    // Sync server-configured booking limit (only if user hasn't overridden it yet)
    if (data.max_booking_hours !== undefined && !localStorage.getItem(LS_BOOKING_LIMIT)) {
      const mh = data.max_booking_hours;
      setBookingLimit(mh === null ? 'unlimited' : mh === 0 ? 'never' : (mh as number));
    }
    // Sync server-configured default user (only if none stored yet)
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

// ── Boards (Inventory) ────────────────────────────────────────────────────────

export async function listBoards(): Promise<BoardInfo[]> {
  const { data } = await api().get<BoardInfo[]>('/boards');
  return data;
}

export async function getBoard(id: string): Promise<BoardInfo> {
  const { data } = await api().get<BoardInfo>(`/boards/${id}`);
  return data;
}

export async function createBoard(body: BoardCreate, username: string): Promise<BoardInfo> {
  const { data } = await apiAs(username).post<BoardInfo>('/boards', body);
  return data;
}

export async function updateBoard(
  id: string,
  body: Partial<BoardCreate>,
  username: string,
): Promise<BoardInfo> {
  const { data } = await apiAs(username).patch<BoardInfo>(`/boards/${id}`, body);
  return data;
}

export async function deleteBoard(id: string): Promise<void> {
  await api().delete(`/boards/${id}`);
}

export async function updateBoardNotes(id: string, notes: string): Promise<BoardInfo> {
  const { data } = await api().patch<BoardInfo>(`/boards/${id}`, { current_notes: notes });
  return data;
}

// ── Tools ─────────────────────────────────────────────────────────────────────

export async function listTools(boardId: string): Promise<ToolInfo[]> {
  const { data } = await api().get<ToolInfo[]>(`/boards/${boardId}/tools`);
  return data;
}

export async function addTool(
  boardId: string,
  body: ToolCreate,
  username: string,
): Promise<ToolInfo> {
  const { data } = await apiAs(username).post<ToolInfo>(`/boards/${boardId}/tools`, body);
  return data;
}

export async function deleteTool(toolId: string, username: string): Promise<void> {
  await apiAs(username).delete(`/tools/${toolId}`);
}

// ── Bookings ──────────────────────────────────────────────────────────────────

export async function bookBoard(
  boardId: string,
  durationHours: number,
  comment: string,
  username: string,
): Promise<BookingInfo> {
  const { data } = await apiAs(username).post<BookingInfo>(`/boards/${boardId}/book`, {
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
  board_id?: string;
  username?: string;
  active?: boolean;
  skip?: number;
  limit?: number;
}): Promise<BookingInfo[]> {
  const { data } = await api().get<BookingInfo[]>('/bookings', { params });
  return data;
}

export async function listActivity(params?: {
  board_id?: string;
  username?: string;
  action?: string;
  skip?: number;
  limit?: number;
}): Promise<ActivityEntry[]> {
  const { data } = await api().get<ActivityEntry[]>('/activity', { params });
  return data;
}
