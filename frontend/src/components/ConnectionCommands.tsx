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
    <div className="bg-gray-900 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-2.5 pb-1.5 border-b border-gray-800">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">{label}</span>
        <button
          onClick={copy}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white transition-colors px-2 py-0.5 rounded hover:bg-gray-700"
          title="Copy"
        >
          {copied
            ? <><Check size={12} className="text-green-400" /><span className="text-green-400">Copied</span></>
            : <><Copy size={12} /><span>Copy</span></>}
        </button>
      </div>
      <div className="flex items-start gap-2 px-4 py-3">
        <span className="text-gray-600 select-none font-mono text-sm mt-0.5">$</span>
        <pre className="text-green-400 font-mono text-sm whitespace-pre-wrap break-all flex-1">{cmd}</pre>
      </div>
    </div>
  );
}

export default function ConnectionCommands({ commands }: { commands: CommandsInfo }) {
  const lines: [string, string][] = ([
    ['SSH', commands.ssh],
    ['UART', commands.uart],
    ['JTAG', commands.jtag_connect],
    ['Vivado TCL', commands.vivado_tcl],
    ['Power on', commands.power_on],
  ] as [string, string][]).filter(([, cmd]) => cmd);

  return (
    <div className="flex flex-col gap-2">
      {lines.map(([label, cmd]) => (
        <ShellLine key={label} label={label} cmd={cmd} />
      ))}
    </div>
  );
}
