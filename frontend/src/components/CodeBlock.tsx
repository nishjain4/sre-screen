import { Check, Copy } from 'lucide-react';
import { useFlag } from '../hooks/useUtils';
import { copyText } from '../utils/clipboard';

export function CopyButton({ text, label = 'Copy', className }: { text: string; label?: string; className?: string }) {
  const [copied, flag] = useFlag();
  return (
    <button
      type="button"
      className={`icon-btn${className ? ` ${className}` : ''}`}
      onClick={async (event) => {
        event.stopPropagation();
        if (await copyText(text)) flag();
      }}
      aria-label={copied ? 'Copied' : label}
      title={copied ? 'Copied' : label}
    >
      {copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
    </button>
  );
}

/** Monospace block with a copy button. */
export function CodeBlock({ code, label, maxHeight }: { code: string; label?: string; maxHeight?: number }) {
  return (
    <div className="code-block">
      {label && <div className="code-block__label">{label}</div>}
      <pre className="code-block__pre" style={maxHeight ? { maxHeight } : undefined}>
        <code>{code}</code>
      </pre>
      <CopyButton text={code} className="code-block__copy" />
    </div>
  );
}

export function stringifyJson(value: unknown): string {
  if (value === undefined) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** Pretty-printed JSON, scrollable. */
export function JsonBlock({ value, label, maxHeight = 320 }: { value: unknown; label?: string; maxHeight?: number }) {
  const text = stringifyJson(value);
  if (!text) {
    return (
      <div className="code-block code-block--empty">
        {label && <div className="code-block__label">{label}</div>}
        <span className="muted">No data</span>
      </div>
    );
  }
  return <CodeBlock code={text} label={label} maxHeight={maxHeight} />;
}
