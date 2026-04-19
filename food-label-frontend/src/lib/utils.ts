import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  /** 合并条件 className，并解决 Tailwind 冲突类。 */
  return twMerge(clsx(inputs));
}
