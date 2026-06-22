import { useQuery } from '@tanstack/react-query';
import { getServerInfo } from '../api/client';

export default function AppHeader() {
  const { data } = useQuery({
    queryKey: ['serverInfo'],
    queryFn: getServerInfo,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });

  const appName = data?.app_name ?? 'BOARDFARM';
  const serverVersion = data?.version ?? '…';

  return (
    <header className="bg-gray-900 text-white px-6 py-2 flex items-center justify-between">
      <span className="font-bold tracking-wide text-sm">{appName}</span>
      <div className="flex items-center gap-4 text-xs text-gray-400 font-mono">
        <span title="Server version">server&nbsp;<span className="text-gray-200">{serverVersion}</span></span>
        <span className="text-gray-600">|</span>
        <span title="Client version">client&nbsp;<span className="text-gray-200">{__APP_VERSION__}</span></span>
      </div>
    </header>
  );
}
