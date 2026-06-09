import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  checkHealth,
  getServerUrl,
  getToken,
  getUsername,
  setServerUrl,
  setToken,
  setUsername,
} from '../api/client';

export default function DiscoveryPage() {
  const [url, setUrl] = useState(getServerUrl());
  const [user, setUser] = useState(getUsername());
  const [token, setTokenState] = useState(getToken());
  const [status, setStatus] = useState<'idle' | 'checking' | 'ok' | 'fail'>('idle');
  const navigate = useNavigate();

  async function connect() {
    setStatus('checking');
    const ok = await checkHealth(url);
    if (ok) {
      setServerUrl(url);
      setUsername(user);
      setToken(token);
      setStatus('ok');
      navigate('/boards');
    } else {
      setStatus('fail');
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="bg-white rounded-2xl shadow-lg p-8 w-full max-w-md">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">Boardfarm</h1>
        <p className="text-sm text-gray-500 mb-6">Connect to a boardfarm server</p>

        <div className="flex flex-col gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Server URL
            </label>
            <input
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="http://localhost:8765"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Your name
            </label>
            <input
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={user}
              onChange={(e) => setUser(e.target.value)}
              placeholder="alice"
            />
            <p className="text-xs text-gray-400 mt-1">
              Used to identify you when booking or modifying boards. No password needed.
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Token{' '}
              <span className="font-normal text-gray-400">(optional)</span>
            </label>
            <input
              type="password"
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={token}
              onChange={(e) => setTokenState(e.target.value)}
              placeholder="Leave blank if no token is configured"
            />
            <p className="text-xs text-gray-400 mt-1">
              Only required if the server was configured with a token.
            </p>
          </div>

          {status === 'fail' && (
            <p className="text-sm text-red-600">
              Could not reach server at <code>{url}</code>. Check the URL and try again.
            </p>
          )}

          <button
            onClick={connect}
            disabled={status === 'checking' || !url || !user}
            className="w-full py-2 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {status === 'checking' ? 'Connecting…' : 'Connect →'}
          </button>
        </div>
      </div>
    </div>
  );
}
