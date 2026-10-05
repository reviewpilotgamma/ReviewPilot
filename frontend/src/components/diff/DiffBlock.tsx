import clsx from "clsx";

function lineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "text-muted";
  if (line.startsWith("+")) return "bg-emerald-soft text-emerald";
  if (line.startsWith("-")) return "bg-rose-soft text-rose";
  if (line.startsWith("@@")) return "text-violet";
  return "text-text/80";
}

export function DiffBlock({ text }: { text: string }) {
  const lines = text.replace(/\n$/, "").split("\n");
  return (
    <pre className="my-3 overflow-x-auto rounded-lg border border-border bg-bg py-2 text-xs" data-testid="diff-block">
      <code>
        {lines.map((line, i) => (
          <div key={i} className={clsx("px-3 whitespace-pre", lineClass(line))}>
            {line || " "}
          </div>
        ))}
      </code>
    </pre>
  );
}
