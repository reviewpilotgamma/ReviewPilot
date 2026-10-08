import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { ConnectGithubButton, InstallAppButton } from "@/components/layout/GithubConnect";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useAuth, useToast } from "@/hooks/useAuth";
import { useAppInfo, useInstallations } from "@/hooks/useInstallations";
import { githubApi } from "@/services/endpoints";

/** Dashboard placeholder while the user can see no GitHub App installation. */
export function InstallAppGate() {
  const { data: app } = useAppInfo();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [refreshing, setRefreshing] = useState(false);
  useInstallations({ pollWhileEmpty: true });

  const refresh = async () => {
    setRefreshing(true);
    try {
      queryClient.setQueryData(["installations"], await githubApi.installations(true));
    } catch (error) {
      toast.error(error instanceof Error && error.message ? error.message : "Could not refresh installations");
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <Card title="Welcome to ReviewPilot">
      <div className="space-y-4">
        <div className="flex gap-3 rounded-xl border border-amber/40 bg-amber-soft p-4">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber" />
          <div className="text-sm">
            <p className="font-medium text-ink">Install the GitHub App first to see your data on the dashboard.</p>
            <p className="mt-1 text-muted">
              {user?.github_linked
                ? `Your GitHub account @${user.github_login ?? ""} is connected, but it can't see any ReviewPilot installation yet.`
                : "Your dashboard stays empty until you install the ReviewPilot GitHub App and connect your GitHub account."}
            </p>
          </div>
        </div>
        <p className="text-sm text-muted">
          Install the ReviewPilot GitHub App on the repositories you want reviewed. ReviewPilot only sees repositories
          you grant it access to.
        </p>
        <div className="flex flex-wrap gap-2">
          <InstallAppButton />
          <ConnectGithubButton />
          <Button variant="ghost" loading={refreshing} icon={<RefreshCw className="h-4 w-4" />} onClick={refresh}>
            Refresh
          </Button>
        </div>
        {!app?.configured && (
          <p className="text-xs text-amber">The GitHub App is not configured yet. Ask an admin to complete Settings.</p>
        )}
      </div>
    </Card>
  );
}
