import { Check, Copy } from 'lucide-react';
import { useState } from 'react';
import type { CommandsInfo } from '../api/types';

function ShellLine({ label, cmd }: { label: string; cmd: string }) {
  const [copied, setCopied] = useState(false);
  function copy() {
    navigator.clipboard.writeText(cmd).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }
  return (
    <div className="group">
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{label}</span>
        <button onClick={copy} className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-500 hover:text-white" title="Copy">
          {copied ? <Check size={13} className="text-green-400" /> : <Copy size={13} />}
        </button>
      </div>
      <div className="flex items-start gap-2 px-4 pb-3">
        <span className="text-gray-500 select-none font-mono text-sm mt-0.5">$</span>
        <pre className="text-green-400 font-mono text-sm whitespace-pre-wrap break-all flex-1">{cmd}</pre>
      </div>
    </div>
  );
}

export default function ConnectionCommands({ commands }: { commands: CommandsInfo }) {
  const lines: [string, string][] = [
    ['SSH', commands.ssh],
    ['UART', commands.uart],
    ['JTAG', commands.jtag_connect],
    ['Vivado TCL', commands.vivado_tcl],
    ['Power on', commands.power_on],
  ].filter(([, cmd]) => cmd) as [string, string][];

  return (
    <div className="bg-gray-900 rounded-xl overflow-hidden divide-y divide-gray-800">
      {lines.map(([label, cmd]) => (
        <ShellLine key={label} label={label} cmd={cmd} />
      ))}
    </div>
  );
}
