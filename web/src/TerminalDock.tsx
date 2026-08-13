import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { Box, ChevronDown, ChevronUp, MessageCircle, Plus, Power, SquareTerminal, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { closeAllTerminals, closeTerminal, createTerminal, listTerminals } from "./api";
import type { DiscussionRequest } from "./discussions";
import type { ResearchLaunchRequest, ResearchNode, TerminalSessionInfo, Workspace } from "./types";

const RESEARCH_START_PROMPT = [
  "You are starting or continuing the project's real research loop as its persistent supervisor. This is research work, not a discussion about how the loop should work.",
  "Run `delta context` and `delta compute show` first. Then follow the complete active LOOP.md and POLICY.md supplied to this session, starting from the first incomplete step.",
  "Use the current research map and policy to choose the next eligible, useful test. Respect any idea-specific instructions and every point where the researcher must be asked.",
  "When execution is needed, start one sealed, bounded piece of work with `delta work start`; do not bypass the saved compute location by running the research command directly. Follow it with `delta work show`. Keep the detailed evidence auditable and update the project research memory after checking the result.",
  "Continue through immediate cycles until an active stop rule, approval boundary, genuine blocker, or ambiguity requires the researcher. Do not stop merely to narrate progress, rehearse Delta Loop, or ask whether you should continue.",
].join("\n\n");

const nodeKindLabels: Record<ResearchNode["kind"], string> = {
  question: "research question",
  direction: "research idea",
  approach: "experiment",
};

function researchStartPrompt(
  workspace: Workspace,
  request: ResearchLaunchRequest,
  focus: ResearchNode | null,
) {
  if (!focus) {
    return `${RESEARCH_START_PROMPT}\n\nThe researcher started this session from the ${request.sourcePage} page without pointing to a specific item in the research map. Consider the whole research map when choosing the next work.`;
  }

  const connections = workspace.research_links.filter((link) => link.source_id === focus.id || link.target_id === focus.id);
  const connectedItems = connections.flatMap((link) => {
    const outgoing = link.source_id === focus.id;
    const other = workspace.nodes.find((node) => node.id === (outgoing ? link.target_id : link.source_id));
    return other ? [`${outgoing ? link.relationship : `${link.relationship} this`}: ${other.title}`] : [];
  });
  const focusDetails = [
    "The researcher pressed the research button while this item was selected on the visual Research page. Treat it as their current focus and begin by considering work in this branch. This is an attention signal, not permission to ignore the active policy or its approval boundaries.",
    `Selected item type: ${nodeKindLabels[focus.kind]}`,
    `Selected item ID: ${focus.id}`,
    `Selected item: ${focus.title}`,
    focus.summary ? `Summary: ${focus.summary}` : "",
    `Status: ${focus.status}`,
    `Potential: ${focus.promise}`,
    `Evidence so far: ${focus.evidence_strength}`,
    connectedItems.length ? `Connected research items: ${connectedItems.join("; ")}` : "No research relationships are recorded for this item yet.",
    focus.kind === "approach" ? `Next work requested in the UI: ${focus.next_work_kind}` : "",
    focus.agent_guidance ? `Special guidance for this item: ${focus.agent_guidance}` : "",
    focus.ask_before ? `Ask the researcher before: ${focus.ask_before}` : "",
  ].filter(Boolean);
  return `${RESEARCH_START_PROMPT}\n\n${focusDetails.join("\n")}`;
}

function additionalChatPrompt(workspace: Workspace, focus: ResearchNode | null) {
  const focusText = focus
    ? `The researcher opened this additional chat while focused on the ${nodeKindLabels[focus.kind]} "${focus.title}" [${focus.id}]. Use that as context, but do not assume what they want changed.`
    : "The researcher opened this additional chat from the project without selecting a specific research item.";
  return [
    "You are an additional Delta Loop discussion session. This chat runs alongside other terminals; do not stop, replace, or take over another session.",
    "Run `delta context` first so you understand the current project and active rules.",
    focusText,
    "Ask one short question about what the researcher wants to discuss. Do not start experiments or edit the research project until they clearly request work in this chat.",
    `Project: ${workspace.name}`,
  ].join("\n\n");
}

type TerminalConnectionState = "connecting" | "connected" | "reconnecting" | "ended";

function TerminalView({
  session,
  onEnded,
  onConnectionChange,
}: {
  session: TerminalSessionInfo;
  onEnded: (sessionId: string) => void;
  onConnectionChange: (state: TerminalConnectionState) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const [readingEarlier, setReadingEarlier] = useState(false);

  useEffect(() => {
    if (!containerRef.current) return;
    setReadingEarlier(false);
    const terminal = new Terminal({
      cursorBlink: true,
      convertEol: false,
      fontFamily: '"SFMono-Regular", Consolas, monospace',
      fontSize: 13,
      lineHeight: 1.3,
      scrollback: 50000,
      scrollOnUserInput: false,
      smoothScrollDuration: 80,
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
    terminalRef.current = terminal;
    fit.fit();

    const socketProtocol = window.location.protocol === "https:" ? "wss" : "ws";
    let decoder = new TextDecoder();
    let disposed = false;
    let socket: WebSocket | null = null;
    let retryTimer: number | null = null;
    let retries = 0;
    let terminalEnded = false;
    let reconnectMessageShown = false;

    const connect = () => {
      if (disposed) return;
      onConnectionChange(retries ? "reconnecting" : "connecting");
      socket = new WebSocket(
        `${socketProtocol}://${window.location.host}/api/terminals/${session.id}/ws`,
      );
      socketRef.current = socket;
      socket.binaryType = "arraybuffer";
      socket.onopen = () => {
        if (retries) {
          terminal.reset();
          decoder = new TextDecoder();
          fit.fit();
        }
        retries = 0;
        reconnectMessageShown = false;
        onConnectionChange("connected");
        terminal.focus();
        socket?.send(JSON.stringify({ type: "resize", columns: terminal.cols, rows: terminal.rows }));
      };
      socket.onmessage = (event) => {
        const output = event.data instanceof ArrayBuffer
          ? decoder.decode(event.data, { stream: true })
          : String(event.data);
        terminal.write(output);
        if (output.includes("[terminal ended]")) terminalEnded = true;
      };
      socket.onclose = (event) => {
        if (disposed) return;
        if (terminalEnded || event.code === 4404) {
          if (event.code === 4404) terminal.writeln("\r\nThis terminal was not found after the server restarted.");
          onConnectionChange("ended");
          onEnded(session.id);
          return;
        }
        if (!reconnectMessageShown) {
          terminal.writeln(event.code === 4409
            ? "\r\nThe terminal is still attached elsewhere. Retrying…"
            : "\r\nConnection interrupted. Reconnecting…");
          reconnectMessageShown = true;
        }
        onConnectionChange("reconnecting");
        retries += 1;
        const delay = Math.min(8000, 500 * (2 ** Math.min(retries, 4)));
        retryTimer = window.setTimeout(connect, delay);
      };
    };
    connect();
    const input = terminal.onData((data) => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "input", data }));
      }
    });
    const resize = terminal.onResize(({ cols, rows }) => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "resize", columns: cols, rows }));
      }
    });
    const scroll = terminal.onScroll(() => {
      if (!session.persistent) {
        setReadingEarlier(terminal.buffer.active.viewportY < terminal.buffer.active.baseY);
      }
    });
    let wheelRemainder = 0;
    const handleWheel = (event: WheelEvent) => {
      if (!event.deltaY) return;
      if (session.persistent) {
        if (event.deltaY < 0) setReadingEarlier(true);
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      const lines = event.deltaMode === WheelEvent.DOM_DELTA_PIXEL
        ? event.deltaY / 24
        : event.deltaMode === WheelEvent.DOM_DELTA_PAGE
          ? event.deltaY * terminal.rows
          : event.deltaY;
      wheelRemainder += lines;
      const wholeLines = wheelRemainder > 0 ? Math.floor(wheelRemainder) : Math.ceil(wheelRemainder);
      if (wholeLines) {
        terminal.scrollLines(wholeLines);
        wheelRemainder -= wholeLines;
      }
    };
    containerRef.current.addEventListener("wheel", handleWheel, { capture: true, passive: false });
    terminal.attachCustomKeyEventHandler((event) => {
      if (session.persistent) return true;
      if (event.type !== "keydown" || !event.shiftKey) return true;
      if (event.key === "ArrowUp") terminal.scrollLines(-3);
      else if (event.key === "ArrowDown") terminal.scrollLines(3);
      else if (event.key === "PageUp") terminal.scrollPages(-1);
      else if (event.key === "PageDown") terminal.scrollPages(1);
      else if (event.key === "Home") terminal.scrollToTop();
      else if (event.key === "End") terminal.scrollToBottom();
      else return true;
      event.preventDefault();
      return false;
    });
    const observer = new ResizeObserver(() => fit.fit());
    observer.observe(containerRef.current);
    return () => {
      disposed = true;
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      observer.disconnect();
      input.dispose();
      resize.dispose();
      scroll.dispose();
      containerRef.current?.removeEventListener("wheel", handleWheel, { capture: true });
      if (socket) {
        socket.onclose = null;
        socket.onmessage = null;
        socket.close(1000);
      }
      if (socketRef.current === socket) socketRef.current = null;
      terminalRef.current = null;
      terminal.dispose();
    };
  }, [onConnectionChange, onEnded, session.id, session.persistent]);

  return (
    <div className="terminal-screen-wrap">
      <div className="terminal-screen" ref={containerRef} />
      {readingEarlier && (
        <button
          className="terminal-jump-latest"
          onClick={() => {
            terminalRef.current?.scrollToBottom();
            setReadingEarlier(false);
            if (socketRef.current?.readyState === WebSocket.OPEN) {
              socketRef.current.send(JSON.stringify({ type: "latest" }));
            }
          }}
        >
          Latest message
        </button>
      )}
    </div>
  );
}

export default function TerminalDock({
  workspace,
  selectedNode,
  discussion,
  researchStartRequest,
  onResearchSessionChange,
  onResearchStartFinished,
  onExpandedChange,
  onError,
}: {
  workspace: Workspace;
  selectedNode: ResearchNode | null;
  discussion: DiscussionRequest | null;
  researchStartRequest: ResearchLaunchRequest | null;
  onResearchSessionChange: (session: TerminalSessionInfo | null) => void;
  onResearchStartFinished: () => void;
  onExpandedChange: (expanded: boolean) => void;
  onError: (message: string) => void;
}) {
  const [sessions, setSessions] = useState<TerminalSessionInfo[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [newMenuOpen, setNewMenuOpen] = useState(false);
  const [confirmStopAll, setConfirmStopAll] = useState(false);
  const [connectionState, setConnectionState] = useState<TerminalConnectionState>("ended");
  const handledDiscussion = useRef<number | null>(null);
  const handledResearchStart = useRef<number | null>(null);
  const openingDiscussion = useRef(false);
  const openingResearch = useRef(false);
  const active = sessions.find((session) => session.id === activeId) ?? null;
  const runningSessions = useMemo(
    () => sessions
      .filter((session) => session.status === "active")
      .slice()
      .sort((a, b) => a.created_at.localeCompare(b.created_at)),
    [sessions],
  );
  const latestResearchSession = useMemo(
    () => sessions
      .filter((session) => session.kind === "research" && session.status === "active")
      .slice()
      .sort((a, b) => b.created_at.localeCompare(a.created_at))[0] ?? null,
    [sessions],
  );

  useEffect(() => {
    onResearchSessionChange(latestResearchSession);
  }, [latestResearchSession, onResearchSessionChange]);

  useEffect(() => {
    onExpandedChange(expanded);
  }, [expanded, onExpandedChange]);

  const refreshSessions = useCallback(() => {
    return listTerminals(workspace.id)
      .then((items) => {
        setSessions(items);
        if (openingDiscussion.current || openingResearch.current) return;
        const running = items
          .filter((item) => item.status === "active")
          .sort((a, b) => b.created_at.localeCompare(a.created_at));
        setActiveId((current) => items.some((item) => item.id === current && item.status === "active")
          ? current
          : running[0]?.id ?? null);
      })
      .catch((caught: unknown) => onError(caught instanceof Error ? caught.message : "Could not load terminals."));
  }, [onError, workspace.id]);

  useEffect(() => {
    refreshSessions();
    const timer = window.setInterval(refreshSessions, 3000);
    return () => window.clearInterval(timer);
  }, [refreshSessions]);

  useEffect(() => {
    if (!discussion || handledDiscussion.current === discussion.id) return;
    handledDiscussion.current = discussion.id;
    openingDiscussion.current = true;
    setBusy(true);
    createTerminal(workspace.id, discussion.nodeId, discussion.prompt, "discussion", discussion.topic)
      .then((session) => {
        setSessions((current) => [...current, session]);
        setActiveId(session.id);
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
        requestedFocus ? `Research · ${requestedFocus.title}` : "Research · whole map",
      ))
      .then((session) => {
        setSessions((current) => current.some((item) => item.id === session.id)
          ? current.map((item) => item.id === session.id ? session : item)
          : [...current, session]);
        setActiveId(session.id);
        setExpanded(true);
      })
      .catch((caught: unknown) => onError(caught instanceof Error ? caught.message : "Could not start the research loop."))
      .finally(() => {
        openingResearch.current = false;
        setBusy(false);
        onResearchStartFinished();
      });
  }, [onError, onResearchStartFinished, researchStartRequest, sessions, workspace]);

  async function openTerminal(alwaysNew = false) {
    setBusy(true);
    setNewMenuOpen(false);
    try {
      const existing = !alwaysNew && sessions.find(
        (session) => session.kind === "shell" && session.status === "active" && session.node_id === selectedNode?.id,
      );
      const title = selectedNode ? `Terminal · ${selectedNode.title}` : "Terminal · project";
      const session = existing || (await createTerminal(workspace.id, selectedNode?.id ?? null, undefined, "shell", title));
      if (!existing) setSessions((current) => [...current, session]);
      setActiveId(session.id);
      setExpanded(true);
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not open the terminal.");
    } finally {
      setBusy(false);
    }
  }

  async function openAgentChat() {
    setBusy(true);
    setNewMenuOpen(false);
    try {
      const title = selectedNode ? `Chat · ${selectedNode.title}` : "Chat · project";
      const session = await createTerminal(
        workspace.id,
        selectedNode?.id ?? null,
        additionalChatPrompt(workspace, selectedNode),
        "discussion",
        title,
      );
      setSessions((current) => [...current, session]);
      setActiveId(session.id);
      setExpanded(true);
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not open a new agent chat.");
    } finally {
      setBusy(false);
    }
  }

  async function endTerminal(sessionId = active?.id) {
    if (!sessionId) return;
    await closeTerminal(sessionId);
    const remaining = runningSessions.filter((item) => item.id !== sessionId);
    setSessions((current) => current.map((item) => item.id === sessionId ? { ...item, status: "exited" } : item));
    setActiveId((current) => current === sessionId ? remaining.at(-1)?.id ?? null : current);
    if (!remaining.length) setExpanded(false);
  }

  async function stopAll() {
    setBusy(true);
    try {
      await closeAllTerminals(workspace.id);
      setSessions((current) => current.map((item) => item.status === "active" ? { ...item, status: "exited" } : item));
      setActiveId(null);
      setExpanded(false);
      setConfirmStopAll(false);
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not stop all project terminals.");
    } finally {
      setBusy(false);
    }
  }

  const markTerminalEnded = useCallback((sessionId: string) => {
    setSessions((current) => {
      const updated = current.map((item) => item.id === sessionId ? { ...item, status: "exited" as const } : item);
      const remaining = updated.filter((item) => item.status === "active");
      setActiveId((currentId) => currentId === sessionId ? remaining.at(-1)?.id ?? null : currentId);
      if (!remaining.length) setExpanded(false);
      return updated;
    });
  }, []);

  return (
    <section className={`terminal-dock ${expanded ? "expanded" : ""} ${runningSessions.length ? "has-sessions" : ""}`}>
      <div className="terminal-bar">
        <div className="terminal-heading">
          <SquareTerminal size={15} />
          <strong>Terminals</strong>
          <span>·</span>
          <span>{runningSessions.length} running</span>
          {active && <><span>·</span><span className="terminal-active-title">{active.title}</span></>}
        </div>
        <div className="terminal-controls">
          <div className="terminal-new-control">
            <button onClick={() => setNewMenuOpen((value) => !value)} disabled={busy}>
              <Plus size={14} /> New
            </button>
            {newMenuOpen && (
              <div className="terminal-new-menu">
                <button onClick={openAgentChat}>
                  <MessageCircle size={15} />
                  <span><strong>Agent chat</strong><small>Start another Codex conversation</small></span>
                </button>
                <button onClick={() => openTerminal(true)}>
                  <SquareTerminal size={15} />
                  <span><strong>Terminal</strong><small>Open another command line</small></span>
                </button>
              </div>
            )}
          </div>
          {active ? (
            <>
              <span className={`terminal-state ${expanded ? connectionState : "connected"}`}>
                <span /> {expanded ? connectionState : "running"}
              </span>
              <button onClick={() => setExpanded((value) => !value)}>
                {expanded ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                {expanded ? "Hide" : "Show"}
              </button>
              <button onClick={() => endTerminal()} title="End this terminal"><X size={14} /> End</button>
              {runningSessions.length > 1 && (
                <button className="terminal-stop-all" onClick={() => setConfirmStopAll(true)}><Power size={13} /> Stop all</button>
              )}
            </>
          ) : (
            <span className="terminal-state"><span /> none running</span>
          )}
        </div>
      </div>
      {runningSessions.length > 0 && (
        <div className="terminal-tabs" aria-label="Running terminals">
          {runningSessions.map((session) => (
            <div className={session.id === activeId ? "terminal-tab selected" : "terminal-tab"} key={session.id}>
              <button
                className="terminal-tab-main"
                onClick={() => {
                  setActiveId(session.id);
                  setConnectionState("connecting");
                  setExpanded(true);
                }}
                title={session.title}
              >
                <span className={`terminal-tab-dot ${session.kind}`} />
                <span>{session.title}</span>
                <small>{session.kind === "discussion" ? "chat" : session.kind}</small>
              </button>
              <button className="terminal-tab-end" onClick={() => endTerminal(session.id)} aria-label={`End ${session.title}`} title="End this terminal">
                <X size={11} />
              </button>
            </div>
          ))}
        </div>
      )}
      {confirmStopAll && (
        <div className="terminal-stop-confirm">
          <div>
            <strong>Stop all {runningSessions.length} Delta Loop terminals?</strong>
            <span>This stops their running processes but keeps their saved Codex conversation history.</span>
          </div>
          <button onClick={stopAll} disabled={busy}>Stop all</button>
          <button onClick={() => setConfirmStopAll(false)} disabled={busy}>Cancel</button>
        </div>
      )}
      {expanded && active ? (
        <TerminalView session={active} onEnded={markTerminalEnded} onConnectionChange={setConnectionState} />
      ) : (
        <div className="terminal-preview">
          <span className="prompt">delta</span>
          <span>{active ? `${active.title} is still running.` : "No terminal is running for this project."}</span>
          <button><Box size={13} /> {selectedNode ? "Selection is ready" : "Choose an item first"}</button>
        </div>
      )}
    </section>
  );
}
