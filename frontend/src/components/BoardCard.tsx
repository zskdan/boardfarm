import { MapPin } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { BoardInfo } from '../api/types';
import StatusBadge from './StatusBadge';

export default function BoardCard({ board }: { board: BoardInfo }) {
  return (
    <Link
      to={`/boards/${board.id}`}
      className={`block rounded-xl border p-4 hover:shadow-md transition-shadow ${
        !board.agent_online && board.enabled ? 'opacity-60' : ''
      } ${!board.enabled ? 'opacity-40' : ''}`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="font-semibold text-gray-900 text-sm leading-tight">
          {board.name}
        </h3>
        <StatusBadge
          agentOnline={board.agent_online}
          activeBooking={!!board.active_booking}
          enabled={board.enabled}
        />
      </div>

      {board.description && (
        <p className="text-xs text-gray-500 mb-2 line-clamp-2">{board.description}</p>
      )}

      {board.location && (
        <div className="flex items-center gap-1 text-xs text-gray-400 mb-2">
          <MapPin size={11} />
          {board.location}
        </div>
      )}

      {board.active_booking && (
        <div className="text-xs text-red-600 mb-2">
          Booked by <strong>{board.active_booking.username}</strong>
        </div>
      )}
    </Link>
  );
}
