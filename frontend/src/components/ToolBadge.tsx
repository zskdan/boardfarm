import type { ToolInfo } from '../api/types';

const TYPE_LABELS: Record<string, string> = {
  logic_analyzer: 'Logic Analyzer',
  power_supply: 'Power Supply',
  oscilloscope: 'Oscilloscope',
  debugger: 'Debugger',
};

export default function ToolBadge({ tool }: { tool: ToolInfo }) {
  const label = TYPE_LABELS[tool.type] ?? tool.type;
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-800"
      title={tool.model || tool.connection_detail}
    >
      {label}
      {tool.model && <span className="opacity-70">({tool.model})</span>}
    </span>
  );
}
