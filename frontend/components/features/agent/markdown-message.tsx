import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function MarkdownMessage({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      skipHtml
      components={{
        a: ({ children, href }) => (
          <a
            className="font-semibold text-primary underline underline-offset-4 transition hover:text-primary/80 focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none"
            href={href}
            rel="noreferrer"
            target="_blank"
          >
            {children}
          </a>
        ),
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-primary/50 pl-3 text-muted-foreground">{children}</blockquote>
        ),
        code: ({ children }) => (
          <code className="rounded-md border border-border/70 bg-muted px-1.5 py-0.5 font-mono text-[0.85em] text-foreground">
            {children}
          </code>
        ),
        h1: ({ children }) => <h1 className="text-base font-bold text-foreground">{children}</h1>,
        h2: ({ children }) => <h2 className="text-base font-bold text-foreground">{children}</h2>,
        h3: ({ children }) => <h3 className="text-sm font-bold text-foreground">{children}</h3>,
        li: ({ children }) => <li className="pl-1">{children}</li>,
        ol: ({ children }) => <ol className="my-3 list-decimal space-y-2 pl-5">{children}</ol>,
        p: ({ children }) => <p className="my-3 first:mt-0 last:mb-0">{children}</p>,
        pre: ({ children }) => (
          <pre className="my-3 overflow-x-auto rounded-xl border border-border/70 bg-muted p-3 text-sm">{children}</pre>
        ),
        strong: ({ children }) => <strong className="font-bold text-foreground">{children}</strong>,
        table: ({ children }) => (
          <div className="my-3 overflow-x-auto">
            <table className="w-full min-w-96 border-collapse text-left text-xs">{children}</table>
          </div>
        ),
        tbody: ({ children }) => <tbody className="divide-y divide-border/70">{children}</tbody>,
        td: ({ children }) => <td className="border border-border/70 px-3 py-2 align-top">{children}</td>,
        th: ({ children }) => (
          <th className="border border-border/70 bg-secondary px-3 py-2 font-bold text-foreground">{children}</th>
        ),
        thead: ({ children }) => <thead>{children}</thead>,
        ul: ({ children }) => <ul className="my-3 list-disc space-y-2 pl-5">{children}</ul>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
