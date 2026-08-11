import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { Box, ChevronDown, ChevronUp, Plug, SquareTerminal, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { closeTerminal, createTerminal, listTerminals } from "./api";
import type { DiscussionRequest } from "./discussions";
import type { ResearchLaunchRequest, ResearchNode, TerminalSessionInfo, Workspace } from "./types";

const RESEARCH_START_PROMPT = [
  "You are starting or continuing the project's real research loop as its persistent supervisor. This is research work, not a discussion about how the loop should work.",
  "Run `delta context` first. Then follow the complete active LOOP.md and POLICY.md supplied to this session, starting from the first incomplete step.",
  "Use the current research map and policy to choose the next eligible, useful test. Respect any idea-specific instructions and every point where the researcher must be asked.",
  "When execution is needed, give one sealed, bounded piece of work to a worker. Keep the detailed evidence auditable and update the project research memory after checking the result.",
  "Continue through immediate cycles until an active stop rule, approval boundary, genuine blocker, or ambiguity requires the researcher. Do not stop merely to narrate progress, rehearse Delta Loop, or ask whether you should continue.",
].join("\n\n");

const nodeKindLabels: Record<ResearchNode["kind"], string> = {
  question: "main research question",
  direction: "research direction",
  approach: "way to test the idea",
};

function researchStartPrompt(
  workspace: Workspace,
  request: ResearchLaunchRequest,
  focus: ResearchNode | null,
) {
  if (!focus) {
    return `${RESEARCH_START_PROMPT}\n\nThe researcher started this session from the ${request.sourcePage} page without pointing to a specific item in the research map. Consider the whole research map when choosing the next work.`;
  }

  const parent = focus.parent_id ? workspace.nodes.find((node) => node.id === focus.parent_id) : null;
  const children = workspace.nodes.filter((node) => node.parent_id === focus.id);
  const focusDetails = [
    "The researcher pressed the research button while this item was selected on the visual Research page. Treat it as their current focus and begin by considering work in this branch. This is an attention signal, not permission to ignore the active policy or its approval boundaries.",
    `Selected item type: ${nodeKindLabels[focus.kind]}`,
    `Selected item ID: ${focus.id}`,
    `Selected item: ${focus.title}`,
    focus.summary ? `Summary: ${focus.summary}` : "",
    `Status: ${focus.status}`,
    `Potential: ${focus.promise}`,
    `Evidence so far: ${focus.evidence_strength}`,
    parent ? `Parent item: ${parent.title}` : "",
    children.length ? `Ways currently shown under it: ${children.map((node) => node.title).join("; ")}` : "",
    focus.kind === "approach" ? `Next work requested in the UI: ${focus.next_work_kind}` : "",
    focus.agent_guidance ? `Special guidance for this item: ${focus.agent_guidance}` : "",
    focus.ask_before ? `Ask the researcher before: ${focus.ask_before}` : "",
  ].filter(Boolean);
  return `${RESEARCH_START_PROMPT}\n\n${focusDetails.join("\n")}`;
}

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
  researchStartRequest,
  onResearchSessionChange,
  onResearchStartFinished,
  onError,
}: {
  workspace: Workspace;
  selectedNode: ResearchNode | null;
  discussion: DiscussionRequest | null;
  researchStartRequest: ResearchLaunchRequest | null;
  onResearchSessionChange: (session: TerminalSessionInfo | null) => void;
  onResearchStartFinished: () => void;
  onError: (message: string) => void;
}) {
  const [sessions, setSessions] = useState<TerminalSessionInfo[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [activeTopic, setActiveTopic] = useState<string | null>(null);
  const handledDiscussion = useRef<number | null>(null);
  const handledResearchStart = useRef<number | null>(null);
  const openingDiscussion = useRef(false);
  const openingResearch = useRef(false);
  const active = sessions.find((session) => session.id === activeId) ?? null;
  const latestResearchSession = useMemo(
    () => sessions
      .filter((session) => session.kind === "research")
      .slice()
      .sort((a, b) => b.created_at.localeCompare(a.created_at))[0] ?? null,
    [sessions],
  );

  useEffect(() => {
    onResearchSessionChange(latestResearchSession);
  }, [latestResearchSession, onResearchSessionChange]);

  useEffect(() => {
    listTerminals(workspace.id)
      .then((items) => {
        setSessions(items);
        if (openingDiscussion.current || openingResearch.current) return;
        const matching = items.find(
          (item) => item.kind === "shell" && item.status === "active" && item.node_id === selectedNode?.id,
        );
        setActiveId((current) => items.some((item) => item.id === current && item.status === "active") ? current : matching?.id ?? null);
        if (!matching) setActiveTopic(null);
      })
      .catch((caught: unknown) => onError(caught instanceof Error ? caught.message : "Could not load terminals."));
  }, [onError, selectedNode?.id, workspace.id]);

  useEffect(() => {
    if (!discussion || handledDiscussion.current === discussion.id) return;
    handledDiscussion.current = discussion.id;
    openingDiscussion.current = true;
    setBusy(true);
    createTerminal(workspace.id, discussion.nodeId, discussion.prompt, "discussion")
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

  useEffect(() => {
    if (researchStartRequest === null || handledResearchStart.current === researchStartRequest.id) return;
    handledResearchStart.current = researchStartRequest.id;
    openingResearch.current = true;
    setBusy(true);
    const existing = sessions.find((session) => session.kind === "research" && session.status === "active");
    const requestedFocus = researchStartRequest.nodeId
      ? workspace.nodes.find((node) => node.id === researchStartRequest.nodeId) ?? null
      : null;
    (existing
      ? Promise.resolve(existing)
      : createTerminal(
        workspace.id,
        requestedFocus?.id ?? null,
        researchStartPrompt(workspace, researchStartRequest, requestedFocus),
        "research",
      ))
      .then((session) => {
        setSessions((current) => current.some((item) => item.id === session.id)
          ? current.map((item) => item.id === session.id ? session : item)
          : [...current, session]);
        setActiveId(session.id);
        setActiveTopic(null);
        setExpanded(true);
      })
      .catch((caught: unknown) => onError(caught instanceof Error ? caught.message : "Could not start the research loop."))
      .finally(() => {
        openingResearch.current = false;
        setBusy(false);
        onResearchStartFinished();
      });
  }, [onError, onResearchStartFinished, researchStartRequest, sessions, workspace]);

  async function openTerminal() {
    setBusy(true);
    try {
      const existing = sessions.find(
        (session) => session.kind === "shell" && session.status === "active" && session.node_id === selectedNode?.id,
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

  const activeResearchFocus = active?.kind === "research" && active.node_id
    ? workspace.nodes.find((node) => node.id === active.node_id) ?? null
    : null;

  return (
    <section className={`terminal-dock ${expanded ? "expanded" : ""}`}>
      <div className="terminal-bar">
        <div>
          <SquareTerminal size={15} />
          {active?.kind === "research" ? "Research session" : active?.kind === "discussion" || activeTopic ? "Agent chat" : "Terminal"}
          <span>·</span>
          {active?.kind === "research"
            ? activeResearchFocus ? `Focus: ${activeResearchFocus.title}` : "Whole research map"
            : activeTopic ?? selectedNode?.title ?? "No idea selected"}
        </div>
        <div className="terminal-controls">
          {active ? (
            <>
              <span className="terminal-state connected"><span /> connected</span>
              <button onClick={() => setExpanded((value) => !value)}>
                {expanded ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                {expanded ? "Hide" : "Show"}
              </button>
              <button onClick={endTerminal} title={active.kind === "research" ? "Stop this research session" : "End this terminal"}><X size={14} /> {active.kind === "research" ? "Stop" : "End"}</button>
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
