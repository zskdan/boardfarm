interface ParsedVersion {
  curSha: string;
  isClean: boolean | null;
  refSha: string | undefined;
  detail: string;
}

export function parseDeployedVersion(raw: string): ParsedVersion {
  const nl = raw.indexOf('\n');
  const firstLine = nl === -1 ? raw : raw.slice(0, nl);
  const detail = nl === -1 ? '' : raw.slice(nl + 1);
  const parts = firstLine.split(':');
  if (parts.length >= 2 && (parts[1] === 'clean' || parts[1] === 'dirty')) {
    return { curSha: parts[0], isClean: parts[1] === 'clean', refSha: parts[2], detail };
  }
  // Unrecognised format (e.g. stale "unknown" from old agent) — treat as no data
  return { curSha: '', isClean: null, refSha: undefined, detail };
}

/**
 * Compact version badge for use in tables.
 * Shows "pending…" when version_script is set but no deployed_version yet.
 * Shows green/red/blue sha badge once a version is available.
 */
export function VersionBadge({
  deployedVersion,
  versionScript,
}: {
  deployedVersion: string;
  versionScript: string;
}) {
  if (!versionScript) return null;

  const vp = parseDeployedVersion(deployedVersion || '');

  if (!deployedVersion || !vp.curSha) {
    return (
      <span className="font-mono text-xs px-1.5 py-0.5 rounded border bg-gray-50 text-gray-400 border-gray-200">
        pending…
      </span>
    );
  }
  const cls =
    vp.isClean === true
      ? 'bg-green-50 text-green-700 border-green-200'
      : vp.isClean === false
        ? 'bg-red-50 text-red-700 border-red-200'
        : 'bg-blue-50 text-blue-700 border-blue-200';

  return (
    <span
      className={`font-mono text-xs px-1.5 py-0.5 rounded border flex items-center gap-1 w-fit ${cls}`}
      title={deployedVersion}
    >
      {vp.curSha}
      {vp.isClean === true && <span className="text-green-600">✓</span>}
      {vp.isClean === false && (
        <>
          <span className="text-red-600">✗</span>
          {vp.refSha && <span className="opacity-60 text-xs">ref:{vp.refSha}</span>}
        </>
      )}
    </span>
  );
}
