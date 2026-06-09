import axios from 'axios';
import type {
  AgentInfo,
  BoardCreate,
  BoardInfo,
  BookingInfo,
  CommandsInfo,
  ToolCreate,
  ToolInfo,
} from './types';

// Stored in localStorage: server URL, username, token, booking limit
const LS_SERVER_URL = 'bf_server_url';
const LS_USERNAME = 'bf_username';
const LS_TOKEN = 'bf_token';
const LS_BOOKING_LIMIT = 'bf_booking_limit';

export function getServerUrl(): string {
  return localStorage.getItem(LS_SERVER_URL) ?? 'http://localhost:8765';
}
export function setServerUrl(url: string) {
  localStorage.setItem(LS_SERVER_URL, url);
}
export function getUsername(): string {
  return localStorage.getItem(LS_USERNAME) ?? '';
}
export function setUsername(u: string) {
  localStorage.setItem(LS_USERNAME, u);
}
export function getToken(): string {
  return localStorage.getItem(LS_TOKEN) ?? '';
}
export function setToken(t: string) {
  localStorage.setItem(LS_TOKEN, t);
}

// BookingLimit: a positive integer (hour cap), 'unlimited' (no cap), or 'never' (no expiry)
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

function makeClient() {
  const instance = axios.create({ baseURL: getServerUrl() });
  instance.interceptors.request.use((config) => {
    const token = getToken();
    const user = getUsername();
    if (token) config.headers['X-Token'] = token;
    if (user) config.headers['X-User'] = user;
    return config;
  });
  return instance;
}

// Recreate the client each call so it picks up any URL/token changes.
function api() {
  return makeClient();
}

// ── Health ──────────────────────────────────────────────────────────────────

export async function checkHealth(serverUrl: string): Promise<boolean> {
  try {
    const { data } = await axios.get(`${serverUrl}/health`, { timeout: 5000 });
    // Sync the server's booking limit into localStorage as the default.
    // The user can override it in Settings afterwards.
    if (!localStorage.getItem(LS_BOOKING_LIMIT) && data.max_booking_hours !== undefined) {
      const mh = data.max_booking_hours;
      const limit: BookingLimit =
        mh === null ? 'unlimited' : mh === 0 ? 'never' : (mh as number);
      setBookingLimit(limit);
    }
    return true;
  } catch {
    return false;
  }
}

// ── Agents ──────────────────────────────────────────────────────────────────

export async function listAgents(): Promise<AgentInfo[]> {
  const { data } = await api().get<AgentInfo[]>('/agents');
  return data;
}

// ── Boards (Inventory) ───────────────────────────────────────────────────────

export async function listBoards(): Promise<BoardInfo[]> {
  const { data } = await api().get<BoardInfo[]>('/boards');
  return data;
}

export async function getBoard(id: string): Promise<BoardInfo> {
  const { data } = await api().get<BoardInfo>(`/boards/${id}`);
  return data;
}

export async function createBoard(body: BoardCreate): Promise<BoardInfo> {
  const { data } = await api().post<BoardInfo>('/boards', body);
  return data;
}

export async function updateBoard(
  id: string,
  body: Partial<BoardCreate>,
): Promise<BoardInfo> {
  const { data } = await api().patch<BoardInfo>(`/boards/${id}`, body);
  return data;
}

export async function deleteBoard(id: string): Promise<void> {
  await api().delete(`/boards/${id}`);
}

export async function updateBoardNotes(id: string, notes: string): Promise<BoardInfo> {
  const { data } = await api().patch<BoardInfo>(`/boards/${id}`, { current_notes: notes });
  return data;
}

// ── Tools ────────────────────────────────────────────────────────────────────

export async function listTools(boardId: string): Promise<ToolInfo[]> {
  const { data } = await api().get<ToolInfo[]>(`/boards/${boardId}/tools`);
  return data;
}

export async function addTool(boardId: string, body: ToolCreate): Promise<ToolInfo> {
  const { data } = await api().post<ToolInfo>(`/boards/${boardId}/tools`, body);
  return data;
}

export async function deleteTool(toolId: string): Promise<void> {
  await api().delete(`/tools/${toolId}`);
}

// ── Bookings ─────────────────────────────────────────────────────────────────

export async function bookBoard(
  boardId: string,
  durationHours: number,
  comment = '',
): Promise<BookingInfo> {
  const { data } = await api().post<BookingInfo>(`/boards/${boardId}/book`, {
    duration_hours: durationHours,
    comment,
  });
  return data;
}

export async function releaseBooking(bookingId: string): Promise<BookingInfo> {
  const { data } = await api().delete<BookingInfo>(`/bookings/${bookingId}`);
  return data;
}

export async function extendBooking(
  bookingId: string,
  hours: number,
): Promise<BookingInfo> {
  const { data } = await api().patch<BookingInfo>(`/bookings/${bookingId}/extend`, {
    hours,
  });
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
