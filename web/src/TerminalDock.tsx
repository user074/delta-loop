import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { Box, ChevronDown, ChevronUp, Maximize2, MessageCircle, Minimize2, Plus, Power, SquareTerminal, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { closeAllTerminals, closeTerminal, createTerminal, listTerminals } from "./api";
import type { DiscussionRequest } from "./discussions";
import type { AppPage, ResearchLaunchRequest, ResearchNode, TerminalSessionInfo, Workspace } from "./types";

const RESEARCH_START_PROMPT = [
  "Start or continue the real research loop.",
  "Run `delta context` and `delta compute show`, then follow the active LOOP.md and POLICY.md.",
  "Use `delta work start` for execution. Continue until a stop rule, approval boundary, or blocker applies.",
].join("\n\n");

const nodeKindLabels: Record<ResearchNode["kind"], string> = {
  question: "research question",
  direction: "research idea",
  approach: "research work",
  finding: "finding",
};

function researchStartPrompt(
  request: ResearchLaunchRequest,
  focus: ResearchNode | null,
) {
  if (!focus) {
    return `${RESEARCH_START_PROMPT}\n\nStarted from ${request.sourcePage}; use the whole research map.`;
  }
  return `${RESEARCH_START_PROMPT}\n\nStart from the selected ${nodeKindLabels[focus.kind]}: "${focus.title}" [${focus.id}].`;
}

function additionalChatPrompt(currentPage: AppPage, focus: ResearchNode | null) {
  const focusText = currentPage === "research" && focus
    ? `This chat was opened from Research with this ${nodeKindLabels[focus.kind]} selected: "${focus.title}" [${focus.id}].`
    : currentPage === "policy"
      ? "This chat was opened from Policy. Do not use a selection from another page unless the researcher mentions it."
      : currentPage === "compute"
        ? "This chat was opened from Compute. Do not use a selection from another page."
        : currentPage === "home"
          ? "This chat was opened from Home. Start from the overall project, not a previous selection."
          : "No research item is selected for this chat.";
  return [
    "This is a separate Delta Loop chat. Run `delta context` first.",
    focusText,
    "Ask what the researcher wants to do. Do not start research work unless they request it here.",
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
  onConnectionChange: (sessionId: string, state: TerminalConnectionState) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const readingEarlier = useRef(false);

  useEffect(() => {
    if (!containerRef.current) return;
    readingEarlier.current = false;
    const terminal = new Terminal({
      cursorBlink: true,
      convertEol: false,
      fontFamily: '"SFMono-Regular", Consolas, monospace',
      fontSize: 13,
      lineHeight: 1.3,
      scrollback: 50000,
      scrollOnUserInput: true,
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
    fit.fit();

    const socketProtocol = window.location.protocol === "https:" ? "wss" : "ws";
    let decoder = new TextDecoder();
    let disposed = false;
    let socket: WebSocket | null = null;
    let retryTimer: number | null = null;
    let retries = 0;
    let terminalEnded = false;
    let reconnectMessageShown = false;
    let readyForInput = false;

    const connect = () => {
      if (disposed) return;
      readyForInput = false;
      onConnectionChange(session.id, retries ? "reconnecting" : "connecting");
      fit.fit();
      socket = new WebSocket(
        `${socketProtocol}://${window.location.host}/api/terminals/${session.id}/ws?columns=${terminal.cols}&rows=${terminal.rows}`,
      );
      socket.binaryType = "arraybuffer";
      socket.onopen = () => {
        if (retries) {
          terminal.reset();
          decoder = new TextDecoder();
          fit.fit();
        }
      };
      socket.onmessage = (event) => {
        if (typeof event.data === "string") {
          try {
            const message = JSON.parse(event.data) as { type?: string };
            if (message.type === "ready") {
              readyForInput = true;
              retries = 0;
              reconnectMessageShown = false;
              onConnectionChange(session.id, "connected");
              terminal.focus();
              return;
            }
          } catch {
            // Ordinary terminal text is not JSON and should render below.
          }
        }
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
          onConnectionChange(session.id, "ended");
          onEnded(session.id);
          return;
        }
        if (!reconnectMessageShown) {
          terminal.writeln(event.code === 4409
            ? "\r\nThe terminal is still attached elsewhere. Retrying…"
            : "\r\nConnection interrupted. Reconnecting…");
          reconnectMessageShown = true;
        }
        onConnectionChange(session.id, "reconnecting");
        retries += 1;
        const delay = Math.min(8000, 500 * (2 ** Math.min(retries, 4)));
        retryTimer = window.setTimeout(connect, delay);
      };
    };
    connect();
    const input = terminal.onData((data) => {
      if (readyForInput && socket?.readyState === WebSocket.OPEN) {
        if (readingEarlier.current) {
          if (session.persistent) socket.send(JSON.stringify({ type: "latest" }));
          else terminal.scrollToBottom();
          readingEarlier.current = false;
        }
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
        readingEarlier.current = terminal.buffer.active.viewportY < terminal.buffer.active.baseY;
      }
    });
    let wheelRemainder = 0;
    const sendPersistentScroll = (lines: number) => {
      if (socket?.readyState !== WebSocket.OPEN || !lines) return;
      socket.send(JSON.stringify({ type: "scroll", lines }));
    };
    const handleWheel = (event: WheelEvent) => {
      if (!event.deltaY) return;
      if (session.persistent) {
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
          sendPersistentScroll(wholeLines);
          wheelRemainder -= wholeLines;
          if (wholeLines < 0) readingEarlier.current = true;
        }
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
      if (event.type !== "keydown" || !event.shiftKey) return true;
      if (session.persistent) {
        if (event.key === "ArrowUp") sendPersistentScroll(-3);
        else if (event.key === "ArrowDown") sendPersistentScroll(3);
        else if (event.key === "PageUp") sendPersistentScroll(-terminal.rows);
        else if (event.key === "PageDown") sendPersistentScroll(terminal.rows);
        else if (event.key === "End") {
          socket?.send(JSON.stringify({ type: "latest" }));
          readingEarlier.current = false;
        } else return true;
        if (event.key !== "End") readingEarlier.current = true;
      } else if (event.key === "ArrowUp") terminal.scrollLines(-3);
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
      terminal.dispose();
    };
  }, [onConnectionChange, onEnded, session.id, session.persistent]);

  return <div className="terminal-screen-wrap"><div className="terminal-screen" ref={containerRef} /></div>;
}

export default function TerminalDock({
  workspace,
  selectedNode,
  currentPage,
  discussion,
  researchStartRequest,
  onResearchSessionChange,
  onResearchStartFinished,
  onExpandedChange,
  onError,
}: {
  workspace: Workspace;
  selectedNode: ResearchNode | null;
  currentPage: AppPage;
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
  const [maximized, setMaximized] = useState(false);
  const [busy, setBusy] = useState(false);
  const [newMenuOpen, setNewMenuOpen] = useState(false);
  const [confirmStopAll, setConfirmStopAll] = useState(false);
  const [connectionStates, setConnectionStates] = useState<Record<string, TerminalConnectionState>>({});
  const handledDiscussion = useRef<number | null>(null);
  const handledResearchStart = useRef<number | null>(null);
  const openingDiscussion = useRef(false);
  const openingResearch = useRef(false);
  const active = sessions.find((session) => session.id === activeId) ?? null;
  const connectionState = activeId ? connectionStates[activeId] ?? "connecting" : "ended";
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

  useEffect(() => {
    if (!expanded) setMaximized(false);
  }, [expanded]);

  useEffect(() => {
    if (!maximized) return;
    const restoreOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      setMaximized(false);
    };
    window.addEventListener("keydown", restoreOnEscape, true);
    return () => window.removeEventListener("keydown", restoreOnEscape, true);
  }, [maximized]);

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
        researchStartPrompt(researchStartRequest, requestedFocus),
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
      const pageFocus = currentPage === "research" ? selectedNode : null;
      const existing = !alwaysNew && sessions.find(
        (session) => session.kind === "shell" && session.status === "active" && session.node_id === pageFocus?.id,
      );
      const title = pageFocus ? `Terminal · ${pageFocus.title}` : `Terminal · ${currentPage}`;
      const session = existing || (await createTerminal(workspace.id, pageFocus?.id ?? null, undefined, "shell", title));
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
      const pageFocus = currentPage === "research" ? selectedNode : null;
      const pageLabel = currentPage[0].toUpperCase() + currentPage.slice(1);
      const title = pageFocus ? `Chat · ${pageFocus.title}` : `Chat · ${pageLabel}`;
      const session = await createTerminal(
        workspace.id,
        pageFocus?.id ?? null,
        additionalChatPrompt(currentPage, pageFocus),
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

  const markConnectionState = useCallback((sessionId: string, state: TerminalConnectionState) => {
    setConnectionStates((current) => current[sessionId] === state
      ? current
      : { ...current, [sessionId]: state });
  }, []);

  return (
    <section className={`terminal-dock ${expanded ? "expanded" : ""} ${maximized ? "maximized" : ""} ${runningSessions.length ? "has-sessions" : ""}`}>
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
              {expanded && (
                <button
                  onClick={() => setMaximized((value) => !value)}
                  title={maximized ? "Return the terminal to the bottom of the page" : "Use the whole window for the terminal"}
                >
                  {maximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                  {maximized ? "Restore" : "Full screen"}
                </button>
              )}
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
      {runningSessions.length > 0 && (
        <div className={expanded ? "terminal-view-stack expanded" : "terminal-view-stack"}>
          {runningSessions.map((session) => (
            <div
              className={expanded && session.id === activeId ? "terminal-view-pane active" : "terminal-view-pane"}
              key={session.id}
            >
              <TerminalView
                session={session}
                onEnded={markTerminalEnded}
                onConnectionChange={markConnectionState}
              />
            </div>
          ))}
        </div>
      )}
      {!expanded && (
        <div className="terminal-preview">
          <span className="prompt">delta</span>
          <span>{active ? `${active.title} is still running.` : "No terminal is running for this project."}</span>
          <button><Box size={13} /> {currentPage === "research" && selectedNode ? "Selection is ready" : `${currentPage[0].toUpperCase() + currentPage.slice(1)} context`}</button>
        </div>
      )}
    </section>
  );
}
