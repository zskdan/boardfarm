import { useEffect, useState } from 'react';
import type { BookingInfo } from '../api/types';

function msLeft(endTime: string): number {
  return new Date(endTime + 'Z').getTime() - Date.now();
}

function fmt(ms: number): string {
  if (ms <= 0) return '0:00:00';
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

interface Props {
  booking: BookingInfo;
  onExtend: () => void;
  onRelease: () => void;
  extending: boolean;
  releasing: boolean;
}

export default function BookingTimer({
  booking,
  onExtend,
  onRelease,
  extending,
  releasing,
}: Props) {
  const [remaining, setRemaining] = useState(() => msLeft(booking.end_time));

  useEffect(() => {
    const id = setInterval(() => {
      setRemaining(msLeft(booking.end_time));
    }, 1000);
    return () => clearInterval(id);
  }, [booking.end_time]);

  const urgent = remaining < 10 * 60 * 1000 && remaining > 0;
  const expired = remaining <= 0;

  return (
    <div className="flex flex-col gap-2">
      <div
        className={`text-2xl font-mono font-semibold ${
          expired
            ? 'text-red-600'
            : urgent
              ? 'text-orange-500 animate-pulse'
              : 'text-gray-800'
        }`}
      >
        {expired ? 'Expired' : fmt(remaining)}
      </div>
      <div className="text-xs text-gray-500">
        Until {new Date(booking.end_time + 'Z').toLocaleTimeString()}
      </div>
      <div className="flex gap-2">
        {!booking.extended && !expired && (
          <button
            onClick={onExtend}
            disabled={extending}
            className="px-3 py-1 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {extending ? 'Extending…' : 'Extend +1h'}
          </button>
        )}
        <button
          onClick={onRelease}
          disabled={releasing}
          className="px-3 py-1 text-sm rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
        >
          {releasing ? 'Releasing…' : 'Release'}
        </button>
      </div>
    </div>
  );
}
