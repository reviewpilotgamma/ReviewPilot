import { ExternalLink, Github, Info } from "lucide-react";
import { Button, type ButtonProps } from "@/components/ui/Button";
import { useAppInfo } from "@/hooks/useInstallations";
import { githubConnectUrl } from "@/services/client";

const NOT_CONFIGURED = "GitHub App not configured — ask an admin";

/** Installs the GitHub App; GitHub then returns to the API, which links the GitHub identity to this user. */
export function InstallAppButton({ label = "Install GitHub App", ...rest }: { label?: string } & ButtonProps) {
  const { data: app } = useAppInfo();
  const ready = Boolean(app?.configured);
  return (
    <Button
      icon={<ExternalLink className="h-4 w-4" />}
      disabled={!ready}
      title={ready ? undefined : NOT_CONFIGURED}
      onClick={() => window.location.assign(githubConnectUrl("install"))}
      {...rest}
    >
      {label}
    </Button>
  );
}

/** For accounts where the App is already installed: authorize only, to link the GitHub identity. */
export function ConnectGithubButton(props: ButtonProps) {
  const { data: app } = useAppInfo();
  const ready = Boolean(app?.configured);
  return (
    <Button
      variant="secondary"
      icon={<Github className="h-4 w-4" />}
      disabled={!ready}
      title={ready ? undefined : NOT_CONFIGURED}
      onClick={() => window.location.assign(githubConnectUrl("authorize"))}
      {...props}
    >
      Already installed? Connect GitHub
    </Button>
  );
}

/** Shown on pages other than the dashboard while the user has no GitHub App installation. */
export function InstallBanner() {
  return (
    <div
      role="status"
      className="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-amber/40 bg-amber-soft p-4 text-sm"
    >
      <Info className="h-4 w-4 shrink-0 text-amber" />
      <span className="flex-1 text-ink">Install the GitHub App to see your repositories and reviews here.</span>
      <InstallAppButton size="sm" />
      <ConnectGithubButton size="sm" />
    </div>
  );
}
