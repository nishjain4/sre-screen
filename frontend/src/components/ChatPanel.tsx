import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { ArrowUp, Check, Sparkles, X } from 'lucide-react';
import { errorMessage } from '../api/client';
import type { ChatMessage, Feedback, Investigation } from '../api/types';
import { useFlag } from '../hooks/useUtils';
import { copyText } from '../utils/clipboard';
import { formatDateTime } from '../utils/format';
import { isTerminal } from '../utils/investigation';
import { ErrorBanner, Spinner } from './Feedback';
import { Markdown } from './Markdown';

interface ChatPanelProps {
  investigation: Investigation;
  onSend: (message: string) => Promise<void>;
  onFeedback: (helpful: boolean, comment?: string) => Promise<void>;
}

function introMessage(inv: Investigation): string {
  switch (inv.status) {
    case 'queued':
      return 'Investigation queued. I will start gathering signals in a moment.';
    case 'running': {
      const steps = inv.steps.length;
      return `Investigating… ${steps > 0 ? `${steps} step${steps === 1 ? '' : 's'} so far. ` : ''}Follow along in the Agent Trace — chat unlocks when the investigation finishes.`;
    }
    case 'completed':
      return 'Investigation complete. Ask me about the root cause, evidence, or remediation.';
    case 'failed':
      return 'The investigation failed before completing. You can still ask me about what was collected.';
    case 'cancelled':
      return 'The investigation was cancelled. You can still ask me about what was collected so far.';
  }
}

function buildTranscript(inv: Investigation): string {
  const lines = [`Bot Svc SRE — ${inv.title}`, `Query: ${inv.query}`, `Status: ${inv.status}${inv.outcome ? ` (${inv.outcome})` : ''}`];
  if (inv.report) lines.push(`Root cause: ${inv.report.root_cause.summary}`);
  lines.push('');
  for (const message of inv.chat) {
    lines.push(`[${formatDateTime(message.created_at)}] ${message.role === 'user' ? 'You' : 'SRE'}:`);
    lines.push(message.content, '');
  }
  return lines.join('\n').trim();
}

function Avatar() {
  return (
    <span className="assistant-avatar" aria-hidden="true">
      <Sparkles size={14} />
    </span>
  );
}

function FeedbackBox({ feedback, onSubmit }: { feedback: Feedback | null; onSubmit: ChatPanelProps['onFeedback'] }) {
  const [submitting, setSubmitting] = useState(false);
  const [askComment, setAskComment] = useState(false);
  const [comment, setComment] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = async (helpful: boolean, text?: string) => {
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(helpful, text);
      setAskComment(false);
      setComment('');
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const selected = feedback?.helpful;
  return (
    <div className="feedback-box">
      <p className="feedback-box__question" id="feedback-question">
        Did SRE find the root cause?
      </p>
      <div className="feedback-box__buttons" role="group" aria-labelledby="feedback-question">
        <button
          type="button"
          className={`btn btn--sm btn--feedback-yes${selected === true ? ' is-selected' : ''}`}
          aria-pressed={selected === true}
          disabled={submitting}
          onClick={() => void submit(true)}
        >
          <Check size={14} aria-hidden="true" /> Yes
        </button>
        <button
          type="button"
          className={`btn btn--sm btn--feedback-no${selected === false || askComment ? ' is-selected' : ''}`}
          aria-pressed={selected === false}
          aria-expanded={askComment}
          disabled={submitting}
          onClick={() => setAskComment((v) => !v)}
        >
          <X size={14} aria-hidden="true" /> Not quite
        </button>
        {submitting && <Spinner size={14} label="Submitting feedback" />}
      </div>
      {askComment && (
        <form
          className="feedback-box__comment"
          onSubmit={(event) => {
            event.preventDefault();
            void submit(false, comment);
          }}
        >
          <label htmlFor="feedback-comment" className="sr-only">
            What was missing?
          </label>
          <textarea
            id="feedback-comment"
            rows={2}
            maxLength={4000}
            placeholder="What was missing or wrong? (optional)"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <div className="feedback-box__comment-actions">
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setAskComment(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn--primary btn--sm" disabled={submitting}>
              Send feedback
            </button>
          </div>
        </form>
      )}
      {feedback && !askComment && (
        <p className="feedback-box__thanks" role="status">
          {feedback.helpful ? 'Thanks! Glad SRE found it.' : 'Thanks — your feedback helps improve future investigations.'}
        </p>
      )}
      {error && <p className="inline-error">{error}</p>}
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === 'user') {
    return (
      <div className="chat-msg chat-msg--user">
        <div className="chat-bubble chat-bubble--user">{message.content}</div>
      </div>
    );
  }
  return (
    <div className="chat-msg chat-msg--assistant">
      <Avatar />
      <div className="chat-bubble chat-bubble--assistant">
        <Markdown>{message.content}</Markdown>
      </div>
    </div>
  );
}

export function ChatPanel({ investigation, onSend, onFeedback }: ChatPanelProps) {
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, flagCopied] = useFlag();
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const lastCount = useRef(investigation.chat.length);

  const finished = isTerminal(investigation.status);
  const canSend = finished && !pending;
  const suggestions = investigation.report?.suggested_questions ?? [];
  const showFeedback = investigation.status === 'completed' || (finished && investigation.report !== null);

  // Scroll to the newest message when messages are added or the assistant starts typing.
  useEffect(() => {
    const grew = investigation.chat.length > lastCount.current;
    lastCount.current = investigation.chat.length;
    if ((grew || pending) && scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, [investigation.chat.length, pending]);

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || !canSend) return;
    setPending(true);
    setError(null);
    setDraft('');
    try {
      await onSend(message);
    } catch (err) {
      setError(errorMessage(err));
      setDraft(message);
    } finally {
      setPending(false);
      inputRef.current?.focus();
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void send(draft);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send(draft);
    }
  };

  const running = !finished;

  return (
    <aside className="chat-panel" aria-label="SRE Assistant">
      <header className="chat-panel__header">
        <Avatar />
        <div className="chat-panel__title">
          <strong>SRE Assistant</strong>
          <span className="chat-panel__status">
            <span className={`dot dot--${running ? 'blue' : 'green'}${running ? ' dot--pulse' : ''}`} aria-hidden="true" />
            {running ? 'Investigating…' : pending ? 'Thinking…' : 'Ready'}
          </span>
        </div>
        <button
          type="button"
          className="link-btn chat-panel__copy"
          onClick={async () => {
            if (await copyText(buildTranscript(investigation))) flagCopied();
          }}
        >
          {copied ? 'Copied!' : 'Copy transcript'}
        </button>
      </header>

      <div className="chat-panel__scroll" ref={scrollRef} aria-live="polite">
        <div className="chat-msg chat-msg--assistant">
          <Avatar />
          <div className="chat-bubble chat-bubble--assistant chat-bubble--intro">
            <p>
              {running && <Spinner size={13} />} {introMessage(investigation)}
            </p>
            {showFeedback && <FeedbackBox feedback={investigation.feedback} onSubmit={onFeedback} />}
          </div>
        </div>

        {suggestions.length > 0 && (
          <div className="suggestions">
            <div className="suggestions__heading">Suggested questions</div>
            {suggestions.map((question) => (
              <button
                key={question}
                type="button"
                className="suggestion"
                disabled={!canSend}
                onClick={() => void send(question)}
              >
                {question}
              </button>
            ))}
          </div>
        )}

        {investigation.chat.length > 0 && (
          <div className="chat-history">
            {investigation.chat.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
          </div>
        )}

        {pending && (
          <div className="chat-msg chat-msg--assistant">
            <Avatar />
            <div className="chat-bubble chat-bubble--assistant typing" role="status" aria-label="SRE is typing">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}

        {error && <ErrorBanner compact message={error} />}
      </div>

      <form className="chat-input" onSubmit={onSubmit}>
        <label htmlFor="chat-input" className="sr-only">
          Ask SRE about this investigation
        </label>
        <textarea
          id="chat-input"
          ref={inputRef}
          rows={2}
          maxLength={8000}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={finished ? 'Ask SRE about this investigation…' : 'Chat unlocks when the investigation finishes…'}
          disabled={!finished}
        />
        <div className="chat-input__footer">
          <span className="chat-input__hint">Enter to send · Shift+Enter for new line</span>
          <button
            type="submit"
            className="chat-input__send"
            disabled={!canSend || draft.trim().length === 0}
            aria-label="Send message"
          >
            {pending ? <Spinner size={16} /> : <ArrowUp size={16} aria-hidden="true" />}
          </button>
        </div>
      </form>
    </aside>
  );
}
