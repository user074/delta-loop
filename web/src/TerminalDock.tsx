import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { Box, ChevronDown, ChevronUp, Plug, SquareTerminal, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { closeTerminal, createTerminal, listTerminals } from "./api";
import type { DiscussionRequest } from "./discussions";
import type { ResearchNode, TerminalSessionInfo, Workspace } from "./types";

function TerminalView({ session, onEnded }: { session: TerminalSessionInfo; onEnded: (sessionId: string) => void }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const terminal = new Terminal({
      cursorBlink: true,
      convertEol: true,
      fontFamily: '"SFMono-Regular", Consolas, monospace',
      fontSize: 12,
      lineHeight: 1.25,
      scrollback: 5000,
      theme: {
        background: "#24241f",
        foreground: "#d7d3c9",
        cursor: "#d9ff70",
        selectionBackground: "#5a5a4d",
        black: "#24241f",
        brightGreen: "#d9ff70",
      },
    });
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    terminal.open(containerRef.current);
    fit.fit();

    const socketProtocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(
      `${socketProtocol}://${window.location.host}/api/terminals/${session.id}/ws`,
    );
    socket.binaryType = "arraybuffer";
    const decoder = new TextDecoder();
    let disposed = false;
    socket.onopen = () => {
      terminal.focus();
      socket.send(JSON.stringify({ type: "resize", columns: terminal.cols, rows: terminal.rows }));
    };
    socket.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) terminal.write(decoder.decode(event.data));
      else terminal.write(String(event.data));
    };
    socket.onclose = (event) => {
      if (disposed) return;
      if (event.code === 4409) terminal.writeln("\r\nThis terminal is already open somewhere else.");
      else if (event.code !== 1000) terminal.writeln("\r\nTerminal connection closed.");
      onEnded(session.id);
    };
    const input = terminal.onData((data) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "input", data }));
      }
    });
    const resize = terminal.onResize(({ cols, rows }) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "resize", columns: cols, rows }));
      }
    });
    const observer = new ResizeObserver(() => fit.fit());
    observer.observe(containerRef.current);
    return () => {
      disposed = true;
      observer.disconnect();
      input.dispose();
      resize.dispose();
      socket.onclose = null;
      socket.onmessage = null;
      socket.close(1000);
      terminal.dispose();
    };
  }, [onEnded, session.id]);

  return <div className="terminal-screen" ref={containerRef} />;
}

export default function TerminalDock({
  workspace,
  selectedNode,
  discussion,
  onError,
}: {
  workspace: Workspace;
  selectedNode: ResearchNode | null;
  discussion: DiscussionRequest | null;
  onError: (message: string) => void;
}) {
  const [sessions, setSessions] = useState<TerminalSessionInfo[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [activeTopic, setActiveTopic] = useState<string | null>(null);
  const handledDiscussion = useRef<number | null>(null);
  const openingDiscussion = useRef(false);
  const active = sessions.find((session) => session.id === activeId) ?? null;

  useEffect(() => {
    listTerminals(workspace.id)
      .then((items) => {
        setSessions(items);
        if (openingDiscussion.current) return;
        const matching = items.find(
          (item) => item.status === "active" && item.node_id === selectedNode?.id,
        );
        setActiveId(matching?.id ?? null);
        setActiveTopic(null);
      })
      .catch((caught: unknown) => onError(caught instanceof Error ? caught.message : "Could not load terminals."));
  }, [onError, selectedNode?.id, workspace.id]);

  useEffect(() => {
    if (!discussion || handledDiscussion.current === discussion.id) return;
    handledDiscussion.current = discussion.id;
    openingDiscussion.current = true;
    setBusy(true);
    createTerminal(workspace.id, discussion.nodeId, discussion.prompt)
      .then((session) => {
        setSessions((current) => [...current, session]);
        setActiveId(session.id);
        setActiveTopic(discussion.topic);
        setExpanded(true);
      })
      .catch((caught: unknown) => onError(caught instanceof Error ? caught.message : "Could not open the agent chat."))
      .finally(() => {
        openingDiscussion.current = false;
        setBusy(false);
      });
  }, [discussion, onError, workspace.id]);

  async function openTerminal() {
    setBusy(true);
    try {
      const existing = sessions.find(
        (session) => session.status === "active" && session.node_id === selectedNode?.id,
      );
      const session = existing ?? (await createTerminal(workspace.id, selectedNode?.id ?? null));
      if (!existing) setSessions((current) => [...current, session]);
      setActiveId(session.id);
      setActiveTopic(null);
      setExpanded(true);
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not open the terminal.");
    } finally {
      setBusy(false);
    }
  }

  async function endTerminal() {
    if (!active) return;
    await closeTerminal(active.id);
    setSessions((current) => current.map((item) => item.id === active.id ? { ...item, status: "exited" } : item));
    setActiveId(null);
    setActiveTopic(null);
    setExpanded(false);
  }

  const markTerminalEnded = useCallback((sessionId: string) => {
    setSessions((current) => current.map((item) => item.id === sessionId ? { ...item, status: "exited" } : item));
    setActiveId((current) => current === sessionId ? null : current);
    setActiveTopic(null);
    setExpanded(false);
  }, []);

  return (
    <section className={`terminal-dock ${expanded ? "expanded" : ""}`}>
      <div className="terminal-bar">
        <div>
          <SquareTerminal size={15} />
          {activeTopic ? "Agent chat" : "Terminal"}
          <span>·</span>
          {activeTopic ?? selectedNode?.title ?? "No idea selected"}
        </div>
        <div className="terminal-controls">
          {active ? (
            <>
              <span className="terminal-state connected"><span /> connected</span>
              <button onClick={() => setExpanded((value) => !value)}>
                {expanded ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                {expanded ? "Hide" : "Show"}
              </button>
              <button onClick={endTerminal} title="End this terminal"><X size={14} /> End</button>
            </>
          ) : (
            <button onClick={openTerminal} disabled={busy}>
              <Plug size={14} /> {busy ? "Opening…" : "Open terminal"}
            </button>
          )}
        </div>
      </div>
      {expanded && active ? (
        <TerminalView session={active} onEnded={markTerminalEnded} />
      ) : (
        <div className="terminal-preview">
          <span className="prompt">delta</span>
          <span>{active ? "Terminal is still running while hidden." : "Open a terminal for the selected idea."}</span>
          <button><Box size={13} /> {selectedNode ? "Selected idea is ready" : "Choose an idea first"}</button>
        </div>
      )}
    </section>
  );
}
