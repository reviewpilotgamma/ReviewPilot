import { Search } from "lucide-react";
import { Chip, Select } from "@/components/ui/Controls";
import { VERDICT_LABEL } from "@/lib/format";
import type { Repo, Verdict } from "@/types/api";

export interface FilterValues {
  repo: string;
  author: string;
  verdict: Verdict | "";
  q: string;
}

interface ReviewFiltersProps {
  values: FilterValues;
  repos: Repo[];
  onChange: (patch: Partial<FilterValues>) => void;
}

const VERDICTS: (Verdict | "")[] = ["", "passed", "warning", "critical"];

export function ReviewFilters({ values, repos, onChange }: ReviewFiltersProps) {
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
      <Select
        label="Repository"
        className="lg:w-56"
        value={values.repo}
        onChange={(event) => onChange({ repo: event.target.value })}
      >
        <option value="">All repositories</option>
        {repos.map((repo) => (
          <option key={repo.full_name} value={repo.full_name}>
            {repo.full_name}
          </option>
        ))}
      </Select>
      <div className="lg:w-44">
        <label htmlFor="filter-author" className="label">
          Author
        </label>
        <input
          id="filter-author"
          className="input"
          placeholder="GitHub login"
          value={values.author}
          onChange={(event) => onChange({ author: event.target.value })}
        />
      </div>
      <div className="flex-1">
        <label htmlFor="filter-q" className="label">
          Search titles
        </label>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" />
          <input
            id="filter-q"
            className="input pl-9"
            placeholder="e.g. payment retries"
            value={values.q}
            onChange={(event) => onChange({ q: event.target.value })}
          />
        </div>
      </div>
      <div>
        <span className="label">Verdict</span>
        <div className="flex flex-wrap gap-2">
          {VERDICTS.map((verdict) => (
            <Chip key={verdict || "all"} active={values.verdict === verdict} onClick={() => onChange({ verdict })}>
              {verdict ? VERDICT_LABEL[verdict] : "All"}
            </Chip>
          ))}
        </div>
      </div>
    </div>
  );
}
