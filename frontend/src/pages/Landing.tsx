import { Check, Github, Layers, LogIn, MessageSquareCode, ShieldCheck, X } from "lucide-react";
import { Link } from "react-router-dom";
import { Brand } from "@/components/layout/Brand";
import { MarkdownView } from "@/components/diff/MarkdownView";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/hooks/useAuth";

const FEATURES = [
  {
    icon: Layers,
    title: "Architectural-only focus",
    body: "Ignores formatting nits. Flags module layering, coupling, API contract breaks, async lifecycles and failure modes.",
  },
  {
    icon: MessageSquareCode,
    title: "Team-defined rules",
    body: "Write your standards in plain English per repository — “strict idempotency keys in payment flows”.",
  },
  {
    icon: Github,
    title: "Native GitHub workflow",
    body: "Reviews on PR open or on demand with @review. Everything lives in the pull request conversation.",
  },
];

type Support = true | false | string;
const COMPARISON: [string, Support, Support][] = [
  ["Style & formatting", true, "Ignored unless risky"],
  ["Module boundaries & coupling", false, true],
  ["API contract breaks", false, true],
  ["Async lifecycle & failure modes", false, true],
  ["Team-specific rules in plain English", "Limited", true],
  ["Lives in the PR conversation", "Partial", true],
];

const SAMPLE_COMMENT = `## ✈️ ReviewPilot Architectural Audit

**Verdict:** 🟡 Warning   ·   **Health score:** 6.8/10   ·   **Lines reviewed:** 214

### Executive Summary
Adds retry logic to the payments client. Retries are bounded, but the charge call is not idempotent.

### Architectural Findings
- **Warning** Non-idempotent retries — \`payments/client.py\`: send an idempotency key with each charge.
- **Passed** Dependency direction — the client stays behind the \`PaymentsGateway\` interface.

---
_Triggered via ReviewPilot · Architecture Gatekeeper_`;

function SupportCell({ value }: { value: Support }) {
  if (value === true) return <Check className="mx-auto h-4 w-4 text-emerald" aria-label="Yes" />;
  if (value === false) return <X className="mx-auto h-4 w-4 text-rose" aria-label="No" />;
  return <span className="text-xs text-muted">{value}</span>;
}

export default function Landing() {
  const { user } = useAuth();

  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between p-4 md:p-6">
        <Brand />
        {user ? (
          <Link to="/dashboard">
            <Button size="sm">Go to dashboard</Button>
          </Link>
        ) : (
          <Link to="/login">
            <Button size="sm" icon={<LogIn className="h-4 w-4" />}>
              Sign in
            </Button>
          </Link>
        )}
      </header>

      <main className="mx-auto max-w-6xl px-4 pb-20 md:px-6">
        <section className="py-16 text-center md:py-24">
          <p className="mx-auto mb-4 inline-flex items-center gap-2 rounded-full border border-violet/40 bg-violet-soft px-3 py-1 text-xs text-violet">
            <ShieldCheck className="h-3.5 w-3.5" /> Your automated senior architect
          </p>
          <h1 className="mx-auto max-w-3xl text-4xl font-bold tracking-tight text-ink md:text-6xl">
            Architectural review for <span className="text-violet">every pull request</span>
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-muted md:text-lg">
            ReviewPilot enforces your team's architectural standards, boundary isolation and quality gates directly in
            GitHub — not in the IDE, and not as another linter.
          </p>
        </section>

        <section className="grid gap-4 md:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="glass p-6">
              <Icon className="h-6 w-6 text-violet" />
              <h3 className="mt-3 font-semibold text-ink">{title}</h3>
              <p className="mt-1 text-sm text-muted">{body}</p>
            </div>
          ))}
        </section>

        <section className="mt-16 grid items-start gap-8 lg:grid-cols-2">
          <div>
            <h2 className="text-2xl font-semibold text-ink">Traditional linters vs ReviewPilot</h2>
            <div className="glass mt-4 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">Capability</th>
                    <th className="px-4 py-3 font-medium">Linters</th>
                    <th className="px-4 py-3 font-medium text-violet">ReviewPilot</th>
                  </tr>
                </thead>
                <tbody>
                  {COMPARISON.map(([capability, linter, rp]) => (
                    <tr key={capability} className="border-t border-border">
                      <td className="px-4 py-3 text-ink">{capability}</td>
                      <td className="px-4 py-3 text-center">
                        <SupportCell value={linter} />
                      </td>
                      <td className="px-4 py-3 text-center">
                        <SupportCell value={rp} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div>
            <h2 className="text-2xl font-semibold text-ink">What lands in your PR</h2>
            <div className="glass mt-4 p-5">
              <MarkdownView markdown={SAMPLE_COMMENT} />
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
