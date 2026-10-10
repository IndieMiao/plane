/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function safeLinkUri(uri: string): string | undefined {
  try {
    return ["http:", "https:", "mailto:", "tel:"].includes(new URL(uri, "https://plane.invalid").protocol)
      ? uri
      : undefined;
  } catch {
    return undefined;
  }
}

export default function AttachmentMarkdownContent({ content }: { content: string }) {
  return (
    <div className="attachment-markdown-content min-w-0 text-16 leading-7 break-words text-primary">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        urlTransform={(uri, key) =>
          key === "src" ? (/^(https?:\/\/|\/[^/])/i.test(uri) ? uri : undefined) : safeLinkUri(uri)
        }
        components={{
          h1: ({ children }) => (
            <h1 className="mt-10 mb-6 text-32 leading-tight font-semibold tracking-tight first:mt-0">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="mt-10 mb-4 border-b border-subtle pb-2 text-24 leading-snug font-semibold first:mt-0">
              {children}
            </h2>
          ),
          h3: ({ children }) => <h3 className="mt-8 mb-3 text-20 leading-snug font-semibold">{children}</h3>,
          h4: ({ children }) => <h4 className="mt-6 mb-3 text-18 font-semibold">{children}</h4>,
          h5: ({ children }) => <h5 className="mt-6 mb-2 text-16 font-semibold">{children}</h5>,
          h6: ({ children }) => <h6 className="mt-6 mb-2 text-14 font-semibold text-secondary">{children}</h6>,
          p: ({ children }) => <p className="my-4 leading-7">{children}</p>,
          ul: ({ children, className }) => (
            <ul
              className={
                className === "contains-task-list" ? "my-4 list-none space-y-1" : "my-4 ml-6 list-disc space-y-1"
              }
            >
              {children}
            </ul>
          ),
          ol: ({ children, start }) => (
            <ol start={start} className="my-4 ml-6 list-decimal space-y-1">
              {children}
            </ol>
          ),
          li: ({ children, className }) => <li className={`${className ?? ""} pl-1 [&>p]:my-2`}>{children}</li>,
          input: ({ checked }) => <input type="checkbox" checked={checked} disabled className="mr-2 align-middle" />,
          blockquote: ({ children }) => (
            <blockquote className="my-5 border-l-4 border-strong pl-5 text-secondary [&>p]:my-2">{children}</blockquote>
          ),
          pre: ({ children }) => (
            <pre className="my-5 overflow-x-auto rounded-lg border border-subtle bg-layer-1 p-4 text-13 leading-6 [&>code]:bg-transparent [&>code]:p-0 [&>code]:text-inherit">
              {children}
            </pre>
          ),
          code: ({ className, children }) => (
            <code className={`${className ?? ""} font-mono rounded bg-layer-2 px-1.5 py-0.5 text-[0.9em]`}>
              {children}
            </code>
          ),
          table: ({ children }) => (
            <div className="my-5 overflow-x-auto rounded-lg border border-subtle">
              <table className="w-full border-collapse text-left text-14">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-layer-1">{children}</thead>,
          th: ({ children, style }) => (
            <th style={style} className="border-b border-subtle px-4 py-2.5 font-semibold">
              {children}
            </th>
          ),
          td: ({ children, style }) => (
            <td style={style} className="border-b border-subtle px-4 py-2.5 align-top">
              {children}
            </td>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent-primary underline underline-offset-2"
            >
              {children}
            </a>
          ),
          img: ({ src, alt }) =>
            src ? (
              <img
                src={src}
                alt={alt ?? ""}
                loading="lazy"
                decoding="async"
                className="my-5 h-auto max-w-full rounded-lg"
              />
            ) : (
              <span>{alt}</span>
            ),
          hr: () => <hr className="my-8 border-subtle" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
