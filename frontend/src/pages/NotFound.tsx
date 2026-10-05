import { Compass } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/States";

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <EmptyState
        icon={<Compass className="h-6 w-6" />}
        title="Page not found"
        description="The page you're looking for doesn't exist."
        action={
          <Link to="/">
            <Button variant="secondary">Back home</Button>
          </Link>
        }
      />
    </div>
  );
}
