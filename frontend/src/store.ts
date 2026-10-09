import { create } from "zustand";
import { persist } from "zustand/middleware";
interface Preferences {
  performance: boolean;
  togglePerformance: () => void;
}
export const usePreferences = create<Preferences>()(
  persist(
    (set) => ({
      performance: false,
      togglePerformance: () => set((s) => ({ performance: !s.performance })),
    }),
    { name: "lumi-preferences" },
  ),
);
