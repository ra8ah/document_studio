import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";

/** First-load failure state: never leave the user on an endless "Loading…". */
export default function LoadError({ notFound = false, message, onRetry, testid = "load-error" }) {
  return (
    <div className="py-20 flex flex-col items-center gap-4 text-center" role="alert" data-testid={testid}>
      <div className="headline text-2xl">{notFound ? "Not found" : "Couldn't load this page"}<span className="dotaccent">.</span></div>
      <p className="text-sm text-muted-foreground max-w-sm">
        {message || (notFound ? "It may have been deleted, or the link is wrong." : "Check your connection and try again.")}
      </p>
      {!notFound && onRetry && (
        <Button className="rounded-full gap-2" onClick={onRetry} data-testid={`${testid}-retry`}><RefreshCw size={14} /> Retry</Button>
      )}
    </div>
  );
}
