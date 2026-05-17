import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Edit2, Check, X } from 'lucide-react';
import { updateBoardNotes } from '../api/client';

interface Props {
  boardId: string;
  notes: string;
}

export default function BoardNotes({ boardId, notes }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(notes);
  const qc = useQueryClient();

  const mut = useMutation({
    mutationFn: () => updateBoardNotes(boardId, draft),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['board', boardId] });
      setEditing(false);
    },
  });

  if (!editing) {
    return (
      <div className="flex items-start gap-2">
        <p className="text-sm text-gray-600 flex-1 min-h-[1.5rem]">
          {notes || <span className="text-gray-300 italic">No notes</span>}
        </p>
        <button
          onClick={() => { setDraft(notes); setEditing(true); }}
          className="text-gray-400 hover:text-blue-600 flex-shrink-0"
          title="Edit notes"
        >
          <Edit2 size={14} />
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <textarea
        className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
        rows={3}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="Leave notes for the next user…"
        autoFocus
      />
      <div className="flex gap-2">
        <button
          onClick={() => mut.mutate()}
          disabled={mut.isPending}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        >
          <Check size={12} /> Save
        </button>
        <button
          onClick={() => setEditing(false)}
          className="flex items-center gap-1 px-3 py-1 text-xs border rounded hover:bg-gray-50"
        >
          <X size={12} /> Cancel
        </button>
      </div>
    </div>
  );
}
