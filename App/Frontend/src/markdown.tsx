import { type ReactNode } from "react";

/** Minimal, dependency-free Markdown renderer. All input is escaped first, so
 * journal prose (English, Urdu, Roman Urdu, mixed) renders safely. */
function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderInline(line: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const tokens = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  tokens.forEach((token, index) => {
    if (!token) return;
    if (token.startsWith("**") && token.endsWith("**")) {
      parts.push(<strong key={index}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`") && token.endsWith("`")) {
      parts.push(<code key={index}>{token.slice(1, -1)}</code>);
    } else {
      parts.push(<span key={index}>{token}</span>);
    }
  });
  return parts;
}

export function Markdown({ text }: { text: string }) {
  const lines = (text || "").replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let listBuffer: string[] = [];
  let codeBuffer: string[] = [];

  const flushList = (key: string) => {
    if (!listBuffer.length) return;
    blocks.push(
      <ul key={key}>
        {listBuffer.map((item, index) => (
          <li key={`${key}-${index}`}>{renderInline(item)}</li>
        ))}
      </ul>,
    );
    listBuffer = [];
  };
  const flushCode = (key: string) => {
    if (!codeBuffer.length) return;
    blocks.push(
      <pre key={key}>
        <code>{codeBuffer.join("\n")}</code>
      </pre>,
    );
    codeBuffer = [];
  };

  let blockIndex = 0;
  const nextKey = () => `b${blockIndex++}`;
  lines.forEach((rawLine) => {
    const line = rawLine.trimEnd();
    if (codeBuffer.length || line.startsWith("```")) {
      if (line.startsWith("```")) {
        if (codeBuffer.length) {
          flushCode(nextKey());
        } else {
          codeBuffer.push(line.replace(/^```.*$/, ""));
        }
      } else {
        codeBuffer.push(line);
      }
      return;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      flushList(nextKey());
      flushCode(nextKey());
      const level = heading[1].length;
      const content = renderInline(heading[2]);
      if (level === 1) blocks.push(<h1 key={nextKey()}>{content}</h1>);
      else if (level === 2) blocks.push(<h2 key={nextKey()}>{content}</h2>);
      else if (level === 3) blocks.push(<h3 key={nextKey()}>{content}</h3>);
      else blocks.push(<h4 key={nextKey()}>{content}</h4>);
      return;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      listBuffer.push(line.replace(/^\s*[-*]\s+/, ""));
      return;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      listBuffer.push(line.replace(/^\s*\d+\.\s+/, ""));
      return;
    }
    if (!line.trim()) {
      flushList(nextKey());
      flushCode(nextKey());
      return;
    }
    flushList(nextKey());
    flushCode(nextKey());
    if (line === "---" || line === "***") {
      blocks.push(<hr key={nextKey()} />);
      return;
    }
    blocks.push(<p key={nextKey()}>{renderInline(line)}</p>);
  });
  flushList(nextKey());
  flushCode(nextKey());
  return (
    <div className="markdown" dir="auto">
      {blocks}
    </div>
  );
}

export function initialsOf(name: string): string {
  const words = name.split(/\s+/).filter(Boolean);
  if (words.length > 1) {
    return (words[0][0] + words[words.length - 1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}
