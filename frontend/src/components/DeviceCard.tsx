import { MapPin } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { DeviceInfo } from '../api/types';
import StatusBadge from './StatusBadge';

export default function DeviceCard({ device }: { device: DeviceInfo }) {
  const featureEntries = Object.entries(device.features);
  return (
    <Link
      to={`/devices/${device.id}`}
      className={`block rounded-xl border p-4 hover:shadow-md transition-shadow ${
        !device.agent_online && device.enabled ? 'opacity-60' : ''
      } ${!device.enabled ? 'opacity-40' : ''}`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="font-semibold text-gray-900 text-sm leading-tight">
          {device.name}
        </h3>
        <StatusBadge
          agentOnline={device.agent_online}
          activeBooking={!!device.active_booking}
          enabled={device.enabled}
        />
      </div>

      {device.description && (
        <p className="text-xs text-gray-500 mb-2 line-clamp-2">{device.description}</p>
      )}

      {device.location && (
        <div className="flex items-center gap-1 text-xs text-gray-400 mb-2">
          <MapPin size={11} />
          {device.location}
        </div>
      )}

      {featureEntries.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {featureEntries.map(([k, v]) => (
            <span key={k} className="px-1.5 py-0.5 text-xs rounded bg-gray-100 text-gray-600">
              {k}: {String(v)}
            </span>
          ))}
        </div>
      )}

      {device.active_booking && (
        <div className="text-xs text-red-600 mb-2">
          Booked by <strong>{device.active_booking.username}</strong>
        </div>
      )}
    </Link>
  );
}
