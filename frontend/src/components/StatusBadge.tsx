interface Props {
  agentOnline: boolean;
  activeBooking: boolean;
  enabled: boolean;
  hasAgent?: boolean;
}

export default function StatusBadge({ agentOnline, activeBooking, enabled, hasAgent = false }: Props) {
  if (!enabled) {
    return (
      <span className="px-2 py-0.5 text-xs rounded-full bg-gray-200 text-gray-600">
        Disabled
      </span>
    );
  }
  if (hasAgent && !agentOnline) {
    return (
      <span className="px-2 py-0.5 text-xs rounded-full bg-amber-100 text-amber-700">
        Offline
      </span>
    );
  }
  if (activeBooking) {
    return (
      <span className="px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-700">
        Booked
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 text-xs rounded-full bg-green-100 text-green-700">
      Free
    </span>
  );
}
