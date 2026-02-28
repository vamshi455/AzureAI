import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Bot, User, Copy, Check, ExternalLink, Loader2 } from "lucide-react";
import type { ChatMessage as ChatMessageType, Citation } from "../services/api";

interface ChatMessageProps {
  message: ChatMessageType;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  const isUser = message.role === "user";
  const isStreaming = message.isStreaming && message.role === "assistant";

  const handleCopyCode = async (code: string) => {
    await navigator.clipboard.writeText(code);
    setCopiedCode(code);
    setTimeout(() => setCopiedCode(null), 2000);
  };

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
          isUser ? "bg-blue-600" : "bg-gray-700"
        }`}
      >
        {isUser ? (
          <User className="w-4 h-4 text-white" />
        ) : (
          <Bot className="w-4 h-4 text-white" />
        )}
      </div>

      {/* Message Content */}
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-3 ${
          isUser
            ? "bg-blue-600 text-white"
            : "bg-white border border-gray-200 text-gray-900"
        }`}
      >
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="prose prose-sm max-w-none">
            <ReactMarkdown
              components={{
                // Custom code block rendering with copy button
                code({ className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className || "");
                  const codeString = String(children).replace(/\n$/, "");
                  const isInline = !match && !codeString.includes("\n");

                  if (isInline) {
                    return (
                      <code
                        className="bg-gray-100 text-gray-800 px-1.5 py-0.5 rounded text-xs font-mono"
                        {...props}
                      >
                        {children}
                      </code>
                    );
                  }

                  return (
                    <div className="relative group my-3">
                      {/* Language badge and copy button */}
                      <div className="flex items-center justify-between bg-gray-800 text-gray-300 px-4 py-1.5 rounded-t-lg text-xs">
                        <span>{match?.[1] || "code"}</span>
                        <button
                          onClick={() => handleCopyCode(codeString)}
                          className="flex items-center gap-1 hover:text-white transition-colors"
                        >
                          {copiedCode === codeString ? (
                            <>
                              <Check className="w-3.5 h-3.5" />
                              Copied
                            </>
                          ) : (
                            <>
                              <Copy className="w-3.5 h-3.5" />
                              Copy
                            </>
                          )}
                        </button>
                      </div>
                      <SyntaxHighlighter
                        style={oneDark}
                        language={match?.[1] || "text"}
                        PreTag="div"
                        customStyle={{
                          margin: 0,
                          borderTopLeftRadius: 0,
                          borderTopRightRadius: 0,
                          borderBottomLeftRadius: "0.5rem",
                          borderBottomRightRadius: "0.5rem",
                          fontSize: "0.75rem",
                        }}
                      >
                        {codeString}
                      </SyntaxHighlighter>
                    </div>
                  );
                },

                // Custom table rendering
                table({ children }) {
                  return (
                    <div className="overflow-x-auto my-3">
                      <table className="min-w-full text-xs border border-gray-200 rounded-lg overflow-hidden">
                        {children}
                      </table>
                    </div>
                  );
                },
                thead({ children }) {
                  return <thead className="bg-gray-50">{children}</thead>;
                },
                th({ children }) {
                  return (
                    <th className="px-3 py-2 text-left font-medium text-gray-600 border-b border-gray-200">
                      {children}
                    </th>
                  );
                },
                td({ children }) {
                  return (
                    <td className="px-3 py-2 text-gray-800 border-b border-gray-100">
                      {children}
                    </td>
                  );
                },

                // Custom blockquote
                blockquote({ children }) {
                  return (
                    <blockquote className="border-l-4 border-blue-400 bg-blue-50 pl-4 py-2 my-3 text-sm text-blue-800 rounded-r-lg">
                      {children}
                    </blockquote>
                  );
                },

                // Custom list items
                li({ children }) {
                  return <li className="text-sm text-gray-700 my-0.5">{children}</li>;
                },

                // Headings
                h2({ children }) {
                  return (
                    <h2 className="text-base font-semibold text-gray-900 mt-4 mb-2">
                      {children}
                    </h2>
                  );
                },
                h3({ children }) {
                  return (
                    <h3 className="text-sm font-semibold text-gray-900 mt-3 mb-1.5">
                      {children}
                    </h3>
                  );
                },

                // Paragraphs
                p({ children }) {
                  return <p className="text-sm text-gray-700 my-1.5 leading-relaxed">{children}</p>;
                },

                // Strong/Bold
                strong({ children }) {
                  return <strong className="font-semibold text-gray-900">{children}</strong>;
                },
              }}
            >
              {message.content}
            </ReactMarkdown>

            {/* Streaming indicator */}
            {isStreaming && (
              <div className="flex items-center gap-2 mt-2 text-gray-400">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span className="text-xs">Generating response...</span>
              </div>
            )}

            {/* Citations */}
            {message.citations && message.citations.length > 0 && !isStreaming && (
              <div className="mt-4 pt-3 border-t border-gray-100">
                <div className="text-xs font-medium text-gray-500 mb-2">Sources</div>
                <div className="flex flex-wrap gap-2">
                  {message.citations.map((citation: Citation, index: number) => (
                    <a
                      key={index}
                      href={citation.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-gray-50 border border-gray-200 rounded-lg text-xs text-gray-600 hover:bg-blue-50 hover:border-blue-200 hover:text-blue-700 transition-colors"
                    >
                      <ExternalLink className="w-3 h-3" />
                      <span className="font-medium">[{index + 1}]</span>
                      <span>{citation.title}</span>
                      <span className="text-gray-400">| {citation.source}</span>
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Timestamp */}
        <div
          className={`text-xs mt-1.5 ${
            isUser ? "text-blue-200" : "text-gray-400"
          }`}
        >
          {new Date(message.timestamp).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </div>
      </div>
    </div>
  );
}
