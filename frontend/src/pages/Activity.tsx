import { ChevronDown, ChevronRight, FileWarning, Radio } from "lucide-react";
import { Fragment, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Select } from "@/components/ui/Controls";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/States";
import { Cell, Table } from "@/components/ui/Table";
import { useWorkspace } from "@/hooks/useAuth";
import { useEvents } from "@/hooks/useEvents";
import { eventsApi } from "@/services/endpoints";
import { absoluteTime, prettyJson, relativeTime } from "@/lib/format";
import type { EventStatus, Job, WebhookEvent } from "@/types/api";

const PAGE = 50;
const STATUSES: EventStatus[] = ["queued", "processed", "ignored", "failed"];

function JobError({ job }: { job: Job }) {
  if (!job.last_error) return null;
  if (job.error_code === "diff_too_large") {
    return (
      <div className="mt-2 rounded border border-amber/30 bg-amber-soft p-2 text-xs text-amber">
        <p className="flex items-center gap-1.5 font-medium">
          <FileWarning className="h-3.5 w-3.5 shrink-0" aria-hidden />
          Diff too large for GitHub. Not reviewed. Split the PR into smaller ones.
        </p>
        <details className="mt-1">
          <summary className="cursor-pointer text-muted">Details</summary>
          <p className="mt-1 break-words font-mono text-muted">{job.last_error}</p>
        </details>
      </div>
    );
  }
  return <p className="mt-2 break-words rounded bg-rose-soft p-2 font-mono text-xs text-rose">{job.last_error}</p>;
}

function EventDetails({ event }: { event: WebhookEvent }) {
  return (
    <div className="grid gap-4 bg-bg/60 p-4 lg:grid-cols-2">
      <div>
        <p className="label">Payload preview</p>
        <pre className="max-h-64 overflow-auto rounded-lg border border-border bg-bg p-3 text-xs">
          {prettyJson(event.payload_preview)}
        </pre>
        {event.delivery_id && <p className="mt-2 text-xs text-muted">Delivery {event.delivery_id}</p>}
      </div>
      <div>
        <p className="label">Jobs</p>
        {event.jobs.length === 0 ? (
          <p className="text-sm text-muted">{event.error_message ? `Ignored: ${event.error_message}` : "No jobs"}</p>
        ) : (
          <ul className="space-y-2">
            {event.jobs.map((job) => (
              <li key={job.id} className="rounded-lg border border-border p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{job.kind}</span>
                  <StatusBadge status={job.status} />
                </div>
                <p className="mt-1 text-xs text-muted">
                  Attempt {job.attempts}/{job.max_attempts} · updated {relativeTime(job.updated_at)}
                  {job.review_id && (
                    <>
                      {" · "}
                      <Link to={`/history?review=${job.review_id}`} className="text-violet hover:underline">
                        view review
                      </Link>
                    </>
                  )}
                </p>
                <JobError job={job} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function Activity() {
  const { repos } = useWorkspace();
  const [status, setStatus] = useState<EventStatus | "">("");
  const [repo, setRepo] = useState("");
  const [showBot, setShowBot] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [older, setOlder] = useState<WebhookEvent[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [exhausted, setExhausted] = useState(false);

  const filters = useMemo(
    () => ({ status: status || undefined, repo: repo || undefined, include_bot: showBot || undefined, limit: PAGE }),
    [status, repo, showBot],
  );
  const { data, isLoading, isError, refetch, dataUpdatedAt } = useEvents(filters);

  const resetPaging = () => {
    setOlder([]);
    setExhausted(false);
  };

  // Live page (polled) + older pages loaded on demand, de-duplicated by id.
  const events = useMemo(() => {
    const live = data ?? [];
    const seen = new Set(live.map((e) => e.id));
    return [...live, ...older.filter((e) => !seen.has(e.id))];
  }, [data, older]);

  const loadMore = async () => {
    const last = events[events.length - 1];
    if (!last) return;
    setLoadingMore(true);
    try {
      const page = await eventsApi.list({ ...filters, before_id: last.id });
      setOlder((current) => [...current, ...page]);
      if (page.length < PAGE) setExhausted(true);
    } finally {
      setLoadingMore(false);
    }
  };

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          Webhook activity
          <span className="inline-flex items-center gap-1 text-xs font-normal text-emerald">
            <Radio className="h-3 w-3 animate-pulse" /> live
          </span>
        </span>
      }
      description={dataUpdatedAt ? `Updated ${new Date(dataUpdatedAt).toLocaleTimeString()}` : undefined}
      actions={
        <div className="flex flex-wrap items-center gap-3">
          <label
            className="inline-flex items-center gap-2 text-sm text-muted"
            title="ReviewPilot's own PR comments come back as webhooks and are ignored"
          >
            <input
              type="checkbox"
              className="h-4 w-4 accent-[var(--signal)]"
              checked={showBot}
              onChange={(event) => {
                setShowBot(event.target.checked);
                resetPaging();
              }}
            />
            Show bot events
          </label>
          <Select
            aria-label="Filter by status"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as EventStatus | "");
              resetPaging();
            }}
          >
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Filter by repository"
            value={repo}
            onChange={(event) => {
              setRepo(event.target.value);
              resetPaging();
            }}
          >
            <option value="">All repositories</option>
            {repos.map((r) => (
              <option key={r.full_name} value={r.full_name}>
                {r.full_name}
              </option>
            ))}
          </Select>
        </div>
      }
    >
      {isError ? (
        <ErrorState onRetry={() => void refetch()} />
      ) : !isLoading && events.length === 0 ? (
        <EmptyState
          title="No webhook events yet"
          description="Events appear here as soon as GitHub delivers them to ReviewPilot."
        />
      ) : (
        <>
          <Table head={["", "Time", "Event", "Repository", "Sender", "Status", "Jobs"]}>
            {isLoading ? (
              <SkeletonRows cols={7} />
            ) : (
              events.map((event) => {
                const open = expanded === event.id;
                return (
                  <Fragment key={event.id}>
                    <tr
                      className="cursor-pointer border-t border-border hover:bg-violet-soft/30"
                      onClick={() => setExpanded(open ? null : event.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setExpanded(open ? null : event.id);
                        }
                      }}
                      tabIndex={0}
                      aria-expanded={open}
                    >
                      <Cell className="w-8 text-muted">
                        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                      </Cell>
                      <Cell className="whitespace-nowrap text-muted">
                        <time dateTime={event.created_at} title={absoluteTime(event.created_at)}>
                          {relativeTime(event.created_at)}
                        </time>
                      </Cell>
                      <Cell className="font-mono text-xs">
                        {event.event}
                        {event.action ? `.${event.action}` : ""}
                      </Cell>
                      <Cell className="text-muted">{event.repo ?? "—"}</Cell>
                      <Cell className="text-muted">{event.sender ? `@${event.sender}` : "—"}</Cell>
                      <Cell>
                        <StatusBadge status={event.status} />
                      </Cell>
                      <Cell className="text-xs text-muted">
                        {event.jobs.length ? event.jobs.map((j) => `${j.kind}:${j.status}`).join(", ") : "—"}
                      </Cell>
                    </tr>
                    {open && (
                      <tr>
                        <td colSpan={7}>
                          <EventDetails event={event} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })
            )}
          </Table>
          {events.length >= PAGE && !exhausted && (
            <div className="mt-4 flex justify-center">
              <Button variant="secondary" size="sm" loading={loadingMore} onClick={() => void loadMore()}>
                Load more
              </Button>
            </div>
          )}
        </>
      )}
    </Card>
  );
}
