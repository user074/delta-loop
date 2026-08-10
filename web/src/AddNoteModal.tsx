import { Lightbulb, Plus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { addNote } from "./api";
import type { ResearchNode, Workspace } from "./types";

export default function AddNoteModal({
  open,
  workspace,
  selectedNode,
  onClose,
  onWorkspace,
  onSelect,
  onError,
}: {
  open: boolean;
  workspace: Workspace;
  selectedNode: ResearchNode | null;
  onClose: () => void;
  onWorkspace: (workspace: Workspace) => void;
  onSelect: (nodeId: string) => void;
  onError: (message: string) => void;
}) {
  const [kind, setKind] = useState<"idea" | "way-to-test" | "note" | "question">("idea");
  const [text, setText] = useState("");
  const directions = workspace.nodes.filter((node) => node.kind === "direction");
  const suggestedParent = selectedNode?.kind === "direction"
    ? selectedNode.id
    : selectedNode?.kind === "approach"
      ? selectedNode.parent_id ?? directions[0]?.id ?? ""
      : directions[0]?.id ?? "";
  const [parentId, setParentId] = useState(suggestedParent);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) setParentId(suggestedParent);
  }, [open, suggestedParent]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const before = new Set(workspace.nodes.map((node) => node.id));
      const updated = await addNote(workspace.id, text, kind, kind === "way-to-test" ? parentId : null);
      onWorkspace(updated);
      const created = updated.nodes.find((node) => !before.has(node.id));
      if (created) onSelect(created.id);
      setText("");
      onClose();
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not save the note.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;
  return (
    <div className="modal-backdrop" role="presentation">
      <form className="add-note-card" onSubmit={submit}>
        <button className="modal-close" type="button" onClick={onClose} aria-label="Close"><X size={18} /></button>
        <div className="import-icon"><Lightbulb size={22} /></div>
        <div className="section-kicker">Save a thought quickly</div>
        <h2>Add to the project</h2>
        <p>One sentence is enough. You can add details later.</p>
        <label className="plain-field">
          <span>What are you adding?</span>
          <select value={kind} onChange={(event) => setKind(event.target.value as typeof kind)}>
            <option value="idea">A new idea</option>
            <option value="way-to-test">A way to test an idea</option>
            <option value="question">A question to remember</option>
            <option value="note">A general note</option>
          </select>
        </label>
        {kind === "way-to-test" && (
          <label className="plain-field">
            <span>Which idea does it test?</span>
            <select value={parentId} onChange={(event) => setParentId(event.target.value)}>
              {directions.map((node) => <option key={node.id} value={node.id}>{node.title}</option>)}
            </select>
          </label>
        )}
        <label className="plain-field">
          <span>Your thought</span>
          <textarea autoFocus rows={4} value={text} onChange={(event) => setText(event.target.value)} placeholder="Maybe the difference comes only from…" />
        </label>
        <button className="primary-button" disabled={busy || !text.trim()}><Plus size={16} /> {busy ? "Saving…" : "Save"}</button>
      </form>
    </div>
  );
}
