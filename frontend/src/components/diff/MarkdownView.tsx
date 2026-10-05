import "highlight.js/styles/github-dark.css";
import type { Element, ElementContent } from "hast";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";
import { DiffBlock } from "./DiffBlock";

function textOf(node: ElementContent | Element): string {
  if (node.type === "text") return node.value;
  if ("children" in node) return node.children.map((c) => textOf(c as ElementContent)).join("");
  return "";
}

function isDiffBlock(node: Element | undefined): node is Element {
  const code = node?.children[0];
  if (!code || code.type !== "element" || code.tagName !== "code") return false;
  const classes = code.properties?.className;
  return Array.isArray(classes) && classes.includes("language-diff");
}

const components: Components = {
  pre({ node, children, ...rest }) {
    if (isDiffBlock(node)) return <DiffBlock text={textOf(node)} />;
    return <pre {...rest}>{children}</pre>;
  },
  a({ node: _node, children, ...rest }) {
    return (
      <a {...rest} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  },
};

/**
 * Renders LLM-authored markdown. Raw HTML is intentionally NOT enabled (no rehype-raw):
 * any HTML in the review is shown as text, never executed.
 */
export function MarkdownView({ markdown }: { markdown: string }) {
  return (
    <div className="prose-rp">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: false, plainText: ["diff"] }]]}
        components={components}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
