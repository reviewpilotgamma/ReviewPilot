import { useContext } from "react";
import { AuthContext, type AuthState } from "@/context/AuthContext";
import { ToastContext, type ToastApi } from "@/context/ToastContext";
import { WorkspaceContext, type WorkspaceState } from "@/context/WorkspaceContext";

function required<T>(value: T | null, name: string): T {
  if (value === null) throw new Error(`${name} must be used inside its provider`);
  return value;
}

export const useAuth = (): AuthState => required(useContext(AuthContext), "useAuth");
export const useWorkspace = (): WorkspaceState => required(useContext(WorkspaceContext), "useWorkspace");
export const useToast = (): ToastApi => required(useContext(ToastContext), "useToast");
