import type {
  ChatMessage,
  Feedback,
  FeedbackRequest,
  HealthResponse,
  Investigation,
  InvestigationCreate,
  InvestigationEvent,
  InvestigationEventType,
  InvestigationList,
  ServiceConfig,
  SkillInfo,
  TemplateInfo,
  ToolInfo,
} from './types';

/** "" = same origin (Vite proxy in dev, nginx in Docker). */
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/+$/, '');
const API_KEY = (import.meta.env.VITE_API_KEY ?? '').trim();

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/** FastAPI Swagger UI. */
export const DOCS_URL = apiUrl('/docs');

// --------------------------------------------------------------------------- //
// Errors
// --------------------------------------------------------------------------- //
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError';
}

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message || 'Unexpected error';
  if (typeof err === 'string') return err;
  return 'Unexpected error';
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Turn FastAPI error bodies (`{detail: string | ValidationError[]}`) into a readable message. */
async function readErrorMessage(res: Response): Promise<string> {
  const fallback = `Request failed (${res.status}${res.statusText ? ` ${res.statusText}` : ''})`;
  let text = '';
  try {
    text = await res.text();
  } catch {
    return fallback;
  }
  if (!text) return fallback;
  try {
    const body: unknown = JSON.parse(text);
    if (isRecord(body) && 'detail' in body) {
      const { detail } = body;
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail)) {
        return detail
          .map((item: unknown) => {
            if (!isRecord(item) || typeof item.msg !== 'string') return JSON.stringify(item);
            const loc = Array.isArray(item.loc)
              ? item.loc.filter((part) => part !== 'body').join('.')
              : '';
            return loc ? `${loc}: ${item.msg}` : item.msg;
          })
          .join('; ');
      }
    }
    if (isRecord(body) && typeof body.message === 'string') return body.message;
    return fallback;
  } catch {
    return text.length > 300 ? `${text.slice(0, 300)}…` : text;
  }
}

function buildHeaders(extra?: HeadersInit, accept = 'application/json'): Headers {
  const headers = new Headers(extra);
  if (!headers.has('Accept')) headers.set('Accept', accept);
  if (API_KEY) headers.set('X-API-Key', API_KEY);
  return headers;
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  json?: unknown;
}

async function send(path: string, options: RequestOptions = {}, accept?: string): Promise<Response> {
  const { json, headers: extraHeaders, ...rest } = options;
  const headers = buildHeaders(extraHeaders, accept);
  let body: string | undefined;
  if (json !== undefined) {
    headers.set('Content-Type', 'application/json');
    body = JSON.stringify(json);
  }

  let res: Response;
  try {
    res = await fetch(apiUrl(path), { ...rest, headers, body });
  } catch (err) {
    if (isAbortError(err)) throw err;
    throw new ApiError(
      'Unable to reach the Bot Svc SRE API. Check that the backend is running and reachable.',
      0,
    );
  }
  if (!res.ok) {
    throw new ApiError(await readErrorMessage(res), res.status);
  }
  return res;
}

async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const res = await send(path, options);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  if (!text) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError('The server returned an invalid JSON response.', res.status);
  }
}

// --------------------------------------------------------------------------- //
// Endpoints
// --------------------------------------------------------------------------- //
export interface ListInvestigationsParams {
  limit?: number;
  offset?: number;
  q?: string;
}

function investigationPath(id: string, suffix = ''): string {
  return `/api/investigations/${encodeURIComponent(id)}${suffix}`;
}

export type ExportFormat = 'markdown' | 'json';

function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null;
  const star = /filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i.exec(header);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ''));
    } catch {
      /* fall through */
    }
  }
  const plain = /filename\s*=\s*"?([^";]+)"?/i.exec(header);
  return plain?.[1]?.trim() ?? null;
}

export const api = {
  health: (signal?: AbortSignal) => requestJson<HealthResponse>('/api/health', { signal }),
  config: (signal?: AbortSignal) => requestJson<ServiceConfig>('/api/config', { signal }),
  skills: (signal?: AbortSignal) => requestJson<SkillInfo[]>('/api/skills', { signal }),
  tools: (signal?: AbortSignal) => requestJson<ToolInfo[]>('/api/tools', { signal }),
  templates: (signal?: AbortSignal) => requestJson<TemplateInfo[]>('/api/templates', { signal }),

  listInvestigations: (params: ListInvestigationsParams = {}, signal?: AbortSignal) => {
    const search = new URLSearchParams();
    search.set('limit', String(params.limit ?? 50));
    search.set('offset', String(params.offset ?? 0));
    if (params.q) search.set('q', params.q);
    return requestJson<InvestigationList>(`/api/investigations?${search.toString()}`, { signal });
  },

  getInvestigation: (id: string, signal?: AbortSignal) =>
    requestJson<Investigation>(investigationPath(id), { signal }),

  createInvestigation: (body: InvestigationCreate) =>
    requestJson<Investigation>('/api/investigations', { method: 'POST', json: body }),

  deleteInvestigation: (id: string) =>
    requestJson<void>(investigationPath(id), { method: 'DELETE' }),

  cancelInvestigation: (id: string) =>
    requestJson<Investigation>(investigationPath(id, '/cancel'), { method: 'POST' }),

  chat: (id: string, message: string) =>
    requestJson<ChatMessage>(investigationPath(id, '/chat'), {
      method: 'POST',
      json: { message },
    }),

  feedback: (id: string, body: FeedbackRequest) =>
    requestJson<Feedback>(investigationPath(id, '/feedback'), { method: 'POST', json: body }),

  exportUrl: (id: string, format: ExportFormat) =>
    apiUrl(investigationPath(id, `/export?format=${format}`)),

  /**
   * Download an export. Uses fetch (not a plain link) so the X-API-Key header
   * can be attached when an API key is configured.
   */
  async downloadExport(id: string, format: ExportFormat): Promise<void> {
    const res = await send(investigationPath(id, `/export?format=${format}`), {}, '*/*');
    const blob = await res.blob();
    const filename =
      filenameFromDisposition(res.headers.get('Content-Disposition')) ??
      `investigation-${id}.${format === 'markdown' ? 'md' : 'json'}`;
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.rel = 'noopener';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 2000);
  },
};

// --------------------------------------------------------------------------- //
// Server-Sent Events
// --------------------------------------------------------------------------- //
const EVENT_TYPES: readonly InvestigationEventType[] = [
  'snapshot',
  'status',
  'plan',
  'step',
  'tool_call',
  'timeline',
  'report',
  'chat',
  'done',
];

export interface InvestigationSubscriptionHandlers {
  onEvent: (event: InvestigationEvent) => void;
  /** Connection (re)established. The server always sends a fresh `snapshot` next. */
  onOpen?: () => void;
  /**
   * Connection error. `fatal` is true when the browser gave up (EventSource
   * readyState CLOSED, e.g. non-200 response); otherwise it is auto-reconnecting.
   */
  onError?: (fatal: boolean) => void;
}

/**
 * Subscribe to the investigation's live event stream. EventSource handles
 * reconnects; the stream is closed automatically after the `done` event.
 * Returns an unsubscribe function (idempotent).
 */
export function subscribeToInvestigation(
  id: string,
  handlers: InvestigationSubscriptionHandlers,
): () => void {
  const query = API_KEY ? `?${new URLSearchParams({ api_key: API_KEY }).toString()}` : '';
  const source = new EventSource(apiUrl(investigationPath(id, `/events${query}`)));
  let closed = false;

  const close = () => {
    if (closed) return;
    closed = true;
    source.close();
  };

  for (const type of EVENT_TYPES) {
    source.addEventListener(type, (event: MessageEvent) => {
      if (closed || typeof event.data !== 'string') return;
      let data: unknown;
      try {
        data = JSON.parse(event.data);
      } catch {
        return; // ignore malformed frames
      }
      // The payload shape is defined by the API contract for each event name.
      handlers.onEvent({ type, data } as InvestigationEvent);
      if (type === 'done') close();
    });
  }

  source.onopen = () => {
    if (!closed) handlers.onOpen?.();
  };
  source.onerror = () => {
    if (closed) return;
    const fatal = source.readyState === EventSource.CLOSED;
    if (fatal) close();
    handlers.onError?.(fatal);
  };

  return close;
}
