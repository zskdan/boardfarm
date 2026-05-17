interface Props {
  agentOnline: boolean;
  activeBooking: boolean;
  enabled: boolean;
}

export default function StatusBadge({ agentOnline, activeBooking, enabled }: Props) {
  if (!enabled) {
    return (
      <span className="px-2 py-0.5 text-xs rounded-full bg-gray-200 text-gray-600">
        Disabled
      </span>
    );
  }
  if (!agentOnline) {
    return (
      <span className="px-2 py-0.5 text-xs rounded-full bg-gray-100 text-gray-500">
        Offline
      </span>
    );
  }
  if (activeBooking) {
    return (
      <span className="px-2 py-0.5 text-xs rounded-full bg-red-100 text-red-700">
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
