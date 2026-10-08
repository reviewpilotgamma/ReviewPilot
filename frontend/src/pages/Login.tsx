import { ArrowLeft, LogIn } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Brand } from "@/components/layout/Brand";
import { Button } from "@/components/ui/Button";
import { FullPageSpinner } from "@/components/ui/Spinner";
import { useAuth } from "@/hooks/useAuth";
import { ApiError } from "@/services/client";

const DEFAULT_NEXT = "/dashboard";

/** Only same-site relative paths (prevents open redirects). */
function safeNext(value: string | null): string {
  if (value && value.startsWith("/") && !value.startsWith("//") && !value.includes("\\")) return value;
  return DEFAULT_NEXT;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Invalid username or password";
    if (error.status === 429) return "Too many attempts, try again later";
    return error.message;
  }
  return "Could not sign in, please try again";
}

export default function Login() {
  const { user, isLoading, signIn } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (isLoading) return <FullPageSpinner />;
  if (user && !submitting) return <Navigate to={next} replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await signIn(username, password);
      navigate(next, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between p-4 md:p-6">
        <Brand />
        <Link to="/" className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
          <ArrowLeft className="h-4 w-4" /> Back to home
        </Link>
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pt-10 md:pt-20">
        <form onSubmit={(event) => void submit(event)} className="glass w-full max-w-sm space-y-5 p-6" noValidate>
          <div>
            <h1 className="text-xl font-semibold text-ink">Sign in to ReviewPilot</h1>
            <p className="mt-1 text-sm text-muted">Use the dev or admin account your team was given.</p>
          </div>
          <div>
            <label htmlFor="username" className="label">
              Username
            </label>
            <input
              id="username"
              className="input"
              autoComplete="username"
              autoFocus
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </div>
          <div>
            <label htmlFor="password" className="label">
              Password
            </label>
            <input
              id="password"
              type="password"
              className="input"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          {error && (
            <p role="alert" className="text-sm text-rose">
              {error}
            </p>
          )}
          <Button
            type="submit"
            className="w-full"
            loading={submitting}
            disabled={!username.trim() || !password}
            icon={<LogIn className="h-4 w-4" />}
          >
            Sign in
          </Button>
        </form>
      </main>
    </div>
  );
}
