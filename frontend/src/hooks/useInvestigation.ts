import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import { ApiError, api, errorMessage, isAbortError, subscribeToInvestigation } from '../api/client';
import type {
  ChatMessage,
  Feedback,
  Investigation,
  InvestigationEvent,
  InvestigationStep,
  StatusEventData,
  ToolCall,
} from '../api/types';
import { isTerminal } from '../utils/investigation';

export type ConnectionState = 'idle' | 'connecting' | 'live' | 'reconnecting' | 'closed';

export interface InvestigationState {
  investigation: Investigation | null;
  loading: boolean;
  error: string | null;
  notFound: boolean;
  connection: ConnectionState;
  /** tool_call events that arrived before their step (applied when the step shows up). */
  pendingCalls: Record<string, ToolCall[]>;
}

type Action =
  | { type: 'reset' }
  | { type: 'loaded'; investigation: Investigation }
  | { type: 'load_failed'; error: string; notFound: boolean }
  | { type: 'connection'; value: ConnectionState }
  | { type: 'event'; event: InvestigationEvent }
  | { type: 'chat_append'; message: ChatMessage }
  | { type: 'chat_remove'; id: string }
  | { type: 'feedback'; feedback: Feedback };

const initialState: InvestigationState = {
  investigation: null,
  loading: true,
  error: null,
  notFound: false,
  connection: 'idle',
  pendingCalls: {},
};

// --------------------------------------------------------------------------- //
// Pure state transitions (one per SSE event, see docs/API.md)
// --------------------------------------------------------------------------- //
function upsertCall(calls: ToolCall[], call: ToolCall): ToolCall[] {
  const index = calls.findIndex((c) => c.id === call.id);
  if (index === -1) return [...calls, call];
  const next = calls.slice();
  next[index] = call;
  return next;
}

function upsertStep(steps: InvestigationStep[], step: InvestigationStep): InvestigationStep[] {
  const index = steps.findIndex((s) => s.id === step.id);
  const next = index === -1 ? [...steps, step] : steps.map((s, i) => (i === index ? step : s));
  return next.sort((a, b) => a.index - b.index);
}

function appendChat(chat: ChatMessage[], message: ChatMessage): ChatMessage[] {
  return chat.some((m) => m.id === message.id) ? chat : [...chat, message];
}

function mergeStatus(investigation: Investigation, data: StatusEventData): Investigation {
  const next: Investigation = { ...investigation };
  if (data.status !== undefined) next.status = data.status;
  if (data.outcome !== undefined) next.outcome = data.outcome;
  if (data.title !== undefined && data.title) next.title = data.title;
  if (data.selected_skill_ids !== undefined) next.selected_skill_ids = data.selected_skill_ids;
  if (data.started_at !== undefined) next.started_at = data.started_at;
  if (data.finished_at !== undefined) next.finished_at = data.finished_at;
  if (data.duration_ms !== undefined) next.duration_ms = data.duration_ms;
  if (data.error !== undefined) next.error = data.error;
  return next;
}

function applyEvent(state: InvestigationState, event: InvestigationEvent): InvestigationState {
  if (event.type === 'snapshot') {
    return { ...state, investigation: event.data, loading: false, error: null, notFound: false, pendingCalls: {} };
  }
  const current = state.investigation;
  if (!current) return state; // nothing to merge into until the snapshot arrives

  switch (event.type) {
    case 'status':
      return { ...state, investigation: mergeStatus(current, event.data) };
    case 'plan':
      return { ...state, investigation: { ...current, plan: event.data } };
    case 'step': {
      let step = event.data;
      const pending = state.pendingCalls[step.id];
      let pendingCalls = state.pendingCalls;
      if (pending?.length) {
        step = { ...step, tool_calls: pending.reduce(upsertCall, step.tool_calls) };
        pendingCalls = { ...state.pendingCalls };
        delete pendingCalls[step.id];
      }
      return { ...state, pendingCalls, investigation: { ...current, steps: upsertStep(current.steps, step) } };
    }
    case 'tool_call': {
      const { step_id: stepId, call } = event.data;
      if (!current.steps.some((s) => s.id === stepId)) {
        const queued = state.pendingCalls[stepId] ?? [];
        return { ...state, pendingCalls: { ...state.pendingCalls, [stepId]: upsertCall(queued, call) } };
      }
      const steps = current.steps.map((s) =>
        s.id === stepId ? { ...s, tool_calls: upsertCall(s.tool_calls, call) } : s,
      );
      return { ...state, investigation: { ...current, steps } };
    }
    case 'timeline':
      return { ...state, investigation: { ...current, timeline: event.data } };
    case 'report':
      return { ...state, investigation: { ...current, report: event.data } };
    case 'chat':
      return { ...state, investigation: { ...current, chat: appendChat(current.chat, event.data) } };
    case 'done':
      return {
        ...state,
        connection: 'closed',
        investigation: event.data?.status ? { ...current, status: event.data.status } : current,
      };
  }
}

function reducer(state: InvestigationState, action: Action): InvestigationState {
  switch (action.type) {
    case 'reset':
      return initialState;
    case 'loaded': {
      // Keep optimistic (not yet acknowledged) chat messages across refreshes.
      const previous = state.investigation;
      const localMessages =
        previous && previous.id === action.investigation.id
          ? previous.chat.filter((m) => m.id.startsWith('local-'))
          : [];
      const chat = localMessages.reduce(
        (acc, m) => (acc.some((x) => x.role === m.role && x.content === m.content) ? acc : [...acc, m]),
        action.investigation.chat,
      );
      return {
        ...state,
        investigation: { ...action.investigation, chat },
        loading: false,
        error: null,
        notFound: false,
      };
    }
    case 'load_failed':
      return { ...state, loading: false, error: action.error, notFound: action.notFound };
    case 'connection':
      return state.connection === action.value ? state : { ...state, connection: action.value };
    case 'event':
      return applyEvent(state, action.event);
    case 'chat_append':
      return state.investigation
        ? { ...state, investigation: { ...state.investigation, chat: appendChat(state.investigation.chat, action.message) } }
        : state;
    case 'chat_remove':
      return state.investigation
        ? {
            ...state,
            investigation: {
              ...state.investigation,
              chat: state.investigation.chat.filter((m) => m.id !== action.id),
            },
          }
        : state;
    case 'feedback':
      return state.investigation
        ? { ...state, investigation: { ...state.investigation, feedback: action.feedback } }
        : state;
  }
}

// --------------------------------------------------------------------------- //
// Hook
// --------------------------------------------------------------------------- //
export interface InvestigationActions {
  reload: () => void;
  /** Sends a chat message (optimistic user bubble). Rejects on failure. */
  sendChat: (message: string) => Promise<void>;
  submitFeedback: (helpful: boolean, comment?: string) => Promise<void>;
  cancel: () => Promise<void>;
}

const MAX_RETRY_DELAY_MS = 30_000;

/**
 * Loads an investigation via GET (so unknown ids 404 without opening a stream),
 * then follows it over SSE while it is queued/running.
 */
export function useInvestigation(id: string): { state: InvestigationState; actions: InvestigationActions } {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [reloadKey, bumpReload] = useReducer((n: number) => n + 1, 0);
  const idRef = useRef(id);
  idRef.current = id;

  useEffect(() => {
    if (!id) return undefined;
    let disposed = false;
    let unsubscribe: (() => void) | null = null;
    let retryTimer: number | undefined;
    let attempt = 0;
    const controller = new AbortController();

    dispatch({ type: 'reset' });

    const stopStream = () => {
      unsubscribe?.();
      unsubscribe = null;
    };

    const scheduleRetry = () => {
      if (disposed) return;
      window.clearTimeout(retryTimer);
      const delay = Math.min(MAX_RETRY_DELAY_MS, 2000 * 2 ** attempt);
      attempt += 1;
      dispatch({ type: 'connection', value: 'reconnecting' });
      retryTimer = window.setTimeout(() => void load('retry'), delay);
    };

    const connect = () => {
      if (disposed || unsubscribe) return;
      dispatch({ type: 'connection', value: 'connecting' });
      unsubscribe = subscribeToInvestigation(id, {
        onOpen: () => {
          attempt = 0;
          dispatch({ type: 'connection', value: 'live' });
        },
        onEvent: (event) => {
          if (disposed) return;
          dispatch({ type: 'event', event });
          if (event.type === 'done') {
            unsubscribe = null; // client already closed the EventSource
            // Final consistency refresh in case any event was missed.
            void load('refresh');
          }
        },
        onError: (fatal) => {
          if (disposed) return;
          if (fatal) {
            unsubscribe = null;
            scheduleRetry();
          } else {
            dispatch({ type: 'connection', value: 'reconnecting' });
          }
        },
      });
    };

    async function load(kind: 'initial' | 'retry' | 'refresh') {
      try {
        const investigation = await api.getInvestigation(id, controller.signal);
        if (disposed) return;
        dispatch({ type: 'loaded', investigation });
        if (isTerminal(investigation.status)) {
          stopStream();
          dispatch({ type: 'connection', value: 'closed' });
        } else if (kind !== 'refresh') {
          connect();
        }
      } catch (err) {
        if (disposed || isAbortError(err)) return;
        if (kind === 'initial') {
          dispatch({
            type: 'load_failed',
            error: errorMessage(err),
            notFound: err instanceof ApiError && err.isNotFound,
          });
        } else if (kind === 'retry') {
          scheduleRetry();
        }
      }
    }

    void load('initial');

    return () => {
      disposed = true;
      controller.abort();
      window.clearTimeout(retryTimer);
      stopStream();
    };
  }, [id, reloadKey]);

  const sendChat = useCallback(async (message: string) => {
    const investigationId = idRef.current;
    const optimistic: ChatMessage = {
      id: `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      role: 'user',
      content: message,
      created_at: new Date().toISOString(),
    };
    dispatch({ type: 'chat_append', message: optimistic });
    try {
      const reply = await api.chat(investigationId, message);
      if (idRef.current !== investigationId) return;
      dispatch({ type: 'chat_append', message: reply });
    } catch (err) {
      dispatch({ type: 'chat_remove', id: optimistic.id });
      throw err;
    }
  }, []);

  const submitFeedback = useCallback(async (helpful: boolean, comment?: string) => {
    const investigationId = idRef.current;
    const feedback = await api.feedback(investigationId, { helpful, comment: comment?.trim() || null });
    if (idRef.current === investigationId) dispatch({ type: 'feedback', feedback });
  }, []);

  const cancel = useCallback(async () => {
    const investigationId = idRef.current;
    const investigation = await api.cancelInvestigation(investigationId);
    if (idRef.current === investigationId) dispatch({ type: 'loaded', investigation });
  }, []);

  const actions = useMemo<InvestigationActions>(
    () => ({ reload: bumpReload, sendChat, submitFeedback, cancel }),
    [sendChat, submitFeedback, cancel],
  );

  return { state, actions };
}
