import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * The standard shadcn/ui class-merging helper: clsx resolves conditional
 * classes, tailwind-merge resolves conflicting Tailwind utilities in favor
 * of the last one (so `cn("px-2", condition && "px-4")` doesn't leave both
 * padding utilities fighting in the compiled CSS). Every shadcn component
 * assumes this exists at this path -- see components.json's `utils` alias.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
