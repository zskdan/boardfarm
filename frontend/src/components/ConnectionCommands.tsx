import { Check, Copy } from 'lucide-react';
import { useState } from 'react';
import type { CommandsInfo } from '../api/types';

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button
      onClick={copy}
      className="text-gray-400 hover:text-gray-700 transition-colors"
      title="Copy"
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

interface CommandRowProps {
  label: string;
  value: string;
}

function CommandRow({ label, value }: CommandRowProps) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        {label}
      </span>
      <div className="flex items-start gap-2 bg-gray-900 rounded p-3">
        <pre className="flex-1 text-sm text-green-400 font-mono whitespace-pre-wrap break-all">
          {value}
        </pre>
        <CopyButton text={value} />
      </div>
    </div>
  );
}

export default function ConnectionCommands({ commands }: { commands: CommandsInfo }) {
  return (
    <div className="flex flex-col gap-3">
      <CommandRow label="JTAG (hw_server)" value={commands.jtag_connect} />
      <CommandRow label="Vivado TCL" value={commands.vivado_tcl} />
      <CommandRow label="UART (telnet)" value={commands.uart} />
      <CommandRow label="SSH" value={commands.ssh} />
      <CommandRow label="Power control" value={commands.power_on} />
    </div>
  );
}
