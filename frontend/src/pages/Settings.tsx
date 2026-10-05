import { CheckCircle2, Copy, KeyRound, Plug, XCircle } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { FullPageSpinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/States";
import { useToast } from "@/hooks/useAuth";
import {
  useReplies,
  useSaveReplies,
  useSaveSettings,
  useSettings,
  useValidateGemini,
  useValidateGithub,
} from "@/hooks/useSettings";
import type { Replies, Settings as SettingsData, SettingsInput, ValidationResult } from "@/types/api";

const MODEL_SUGGESTIONS = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"];
const REPLY_FIELDS: { key: keyof Replies; label: string; hint: string }[] = [
  { key: "welcome", label: "Welcome (on-demand mode)", hint: "Placeholders: {author}, {app_name}" },
  { key: "plan", label: "Fallback execution plan", hint: "Used when the AI model is unavailable" },
  { key: "error", label: "Failure notice", hint: "Placeholder: {reason}" },
  { key: "empty_diff", label: "Empty diff", hint: "Posted when a PR has no file changes" },
];

type FormKey = keyof SettingsInput;

function Field({
  label,
  name,
  value,
  onChange,
  disabled,
  secret,
  hint,
  list,
}: {
  label: string;
  name: FormKey;
  value: string;
  onChange: (name: FormKey, value: string) => void;
  disabled: boolean;
  secret?: boolean;
  hint?: ReactNode;
  list?: string;
}) {
  return (
    <div>
      <label htmlFor={`setting-${name}`} className="label">
        {label}
      </label>
      <input
        id={`setting-${name}`}
        className="input font-mono"
        value={value}
        disabled={disabled}
        list={list}
        autoComplete="off"
        spellCheck={false}
        type={secret && value && !value.startsWith("••••") ? "password" : "text"}
        onFocus={(event) => secret && event.target.value.startsWith("••••") && event.target.select()}
        onChange={(event) => onChange(name, event.target.value)}
      />
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

function ResultLine({ result }: { result: ValidationResult | undefined }) {
  if (!result) return null;
  return (
    <p className={`flex items-center gap-2 text-sm ${result.ok ? "text-emerald" : "text-rose"}`} role="status">
      {result.ok ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
      {result.message}
      {result.app_name && <span className="text-muted">· {result.app_name}</span>}
      {typeof result.installations === "number" && (
        <span className="text-muted">· {result.installations} installation(s)</span>
      )}
    </p>
  );
}

function toForm(settings: SettingsData): Required<SettingsInput> {
  return {
    github_app_id: settings.github_app_id,
    github_app_slug: settings.github_app_slug,
    github_webhook_secret: settings.github_webhook_secret,
    github_private_key_path: settings.github_private_key_path,
    github_client_id: settings.github_client_id,
    github_client_secret: settings.github_client_secret,
    gemini_api_key: settings.gemini_api_key,
    gemini_model: settings.gemini_model,
  };
}

function RepliesCard({ readOnly }: { readOnly: boolean }) {
  const { data } = useReplies();
  const save = useSaveReplies();
  const toast = useToast();
  const [form, setForm] = useState<Replies | null>(null);
  useEffect(() => {
    if (data) setForm(data);
  }, [data]);
  if (!form) return null;

  return (
    <Card title="Canned replies" description="Templates ReviewPilot posts on GitHub.">
      <div className="grid gap-4 lg:grid-cols-2">
        {REPLY_FIELDS.map(({ key, label, hint }) => (
          <div key={key}>
            <label htmlFor={`reply-${key}`} className="label">
              {label}
            </label>
            <textarea
              id={`reply-${key}`}
              className="input min-h-[120px] font-mono text-xs"
              value={form[key]}
              maxLength={5000}
              disabled={readOnly}
              onChange={(event) => setForm({ ...form, [key]: event.target.value })}
            />
            <p className="mt-1 text-xs text-muted">{hint}</p>
          </div>
        ))}
      </div>
      {!readOnly && (
        <div className="mt-4 flex justify-end">
          <Button
            loading={save.isPending}
            disabled={REPLY_FIELDS.some(({ key }) => !form[key].trim())}
            onClick={() =>
              save.mutate(form, {
                onSuccess: () => toast.success("Replies saved"),
                onError: (error) => toast.error(error.message || "Could not save replies"),
              })
            }
          >
            Save replies
          </Button>
        </div>
      )}
    </Card>
  );
}

export default function Settings() {
  const { data: settings, isLoading, isError, refetch } = useSettings();
  const save = useSaveSettings();
  const validateGemini = useValidateGemini();
  const validateGithub = useValidateGithub();
  const toast = useToast();
  const [form, setForm] = useState<Required<SettingsInput> | null>(null);

  useEffect(() => {
    if (settings) setForm(toForm(settings));
  }, [settings]);

  if (isLoading || (!form && !isError)) return <FullPageSpinner />;
  if (isError || !settings || !form) return <ErrorState onRetry={() => void refetch()} />;

  const readOnly = !settings.is_admin;
  const onChange = (name: FormKey, value: string) => setForm({ ...form, [name]: value });
  const dirty = JSON.stringify(form) !== JSON.stringify(toForm(settings));

  const submit = () =>
    save.mutate(form, {
      onSuccess: () => toast.success("Settings saved"),
      onError: (error) => toast.error(error.message || "Could not save settings"),
    });

  return (
    <div className="space-y-6">
      {readOnly && (
        <div className="glass flex items-center gap-2 border-amber/40 px-4 py-3 text-sm text-amber">
          <KeyRound className="h-4 w-4" /> Only admins can change settings. Values are shown read-only and secrets are
          masked.
        </div>
      )}

      <Card
        title="GitHub App"
        description="Credentials for webhooks, installation tokens and GitHub sign-in."
        actions={
          !readOnly && (
            <Button
              variant="secondary"
              size="sm"
              icon={<Plug className="h-4 w-4" />}
              loading={validateGithub.isPending}
              onClick={() => validateGithub.mutate()}
            >
              Test connection
            </Button>
          )
        }
      >
        <div className="mb-4 space-y-2">
          <ResultLine result={validateGithub.data} />
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted">Webhook URL:</span>
            <code className="rounded bg-border/70 px-2 py-0.5 text-xs">{settings.webhook_url}</code>
            <Button
              variant="ghost"
              size="sm"
              aria-label="Copy webhook URL"
              icon={<Copy className="h-3.5 w-3.5" />}
              onClick={() =>
                void navigator.clipboard?.writeText(settings.webhook_url).then(() => toast.success("Copied"))
              }
            />
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="App ID" name="github_app_id" value={form.github_app_id} onChange={onChange} disabled={readOnly} />
          <Field
            label="App slug"
            name="github_app_slug"
            value={form.github_app_slug}
            onChange={onChange}
            disabled={readOnly}
          />
          <Field
            label="Webhook secret"
            name="github_webhook_secret"
            value={form.github_webhook_secret}
            onChange={onChange}
            disabled={readOnly}
            secret
          />
          <Field
            label="Private key path"
            name="github_private_key_path"
            value={form.github_private_key_path}
            onChange={onChange}
            disabled={readOnly}
            hint={
              settings.github_private_key_present ? (
                <Badge tone="emerald">key file present</Badge>
              ) : (
                <Badge tone="rose">key file missing</Badge>
              )
            }
          />
          <Field
            label="OAuth client ID"
            name="github_client_id"
            value={form.github_client_id}
            onChange={onChange}
            disabled={readOnly}
          />
          <Field
            label="OAuth client secret"
            name="github_client_secret"
            value={form.github_client_secret}
            onChange={onChange}
            disabled={readOnly}
            secret
          />
        </div>
      </Card>

      <Card
        title="Gemini"
        description={`Reviews include up to ${settings.max_diff_chars.toLocaleString()} diff characters.`}
        actions={
          !readOnly && (
            <Button
              variant="secondary"
              size="sm"
              loading={validateGemini.isPending}
              onClick={() =>
                validateGemini.mutate({
                  api_key: form.gemini_api_key.startsWith("••••") ? undefined : form.gemini_api_key,
                  model: form.gemini_model,
                })
              }
            >
              Validate key
            </Button>
          )
        }
      >
        <div className="mb-4">
          <ResultLine result={validateGemini.data} />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field
            label="API key"
            name="gemini_api_key"
            value={form.gemini_api_key}
            onChange={onChange}
            disabled={readOnly}
            secret
          />
          <Field
            label="Model"
            name="gemini_model"
            value={form.gemini_model}
            onChange={onChange}
            disabled={readOnly}
            list="gemini-models"
          />
          <datalist id="gemini-models">
            {MODEL_SUGGESTIONS.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </div>
      </Card>

      {!readOnly && (
        <div className="flex justify-end gap-2">
          <Button variant="ghost" disabled={!dirty} onClick={() => setForm(toForm(settings))}>
            Discard
          </Button>
          <Button disabled={!dirty} loading={save.isPending} onClick={submit}>
            Save settings
          </Button>
        </div>
      )}

      <RepliesCard readOnly={readOnly} />
    </div>
  );
}
