import { Link } from "react-router-dom";

export function Brand({ to = "/" }: { to?: string }) {
  return (
    <Link to={to} className="flex items-center gap-2 font-semibold tracking-tight">
      <img src="/logo.svg" alt="" className="h-7 w-7" />
      <span>
        Review<span className="text-violet">Pilot</span>
      </span>
    </Link>
  );
}
