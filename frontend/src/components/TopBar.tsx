import { Link } from "react-router-dom";
import { ThemeToggle } from "./ThemeToggle";

export function TopBar() {
  return (
    <div className="sticky top-0 z-40 flex items-center justify-between border-b border-line bg-ground px-6 py-4">
      <Link to="/" className="flex items-center gap-2.5 no-underline">
        <div className="relative h-[30px] w-[30px] shrink-0 rounded-full border-[1.5px] border-accent">
          <span className="absolute left-1/2 top-1/2 h-[1.5px] w-[9px] origin-left animate-spin bg-accent [animation-duration:3.2s]" />
        </div>
        <div>
          <div className="font-display text-[19px] font-extrabold uppercase tracking-wide text-ink">
            Chronotype
          </div>
          <div className="-mt-0.5 text-[11px] uppercase tracking-wider text-ink-faint">
            Motion study console
          </div>
        </div>
      </Link>
      <ThemeToggle />
    </div>
  );
}
