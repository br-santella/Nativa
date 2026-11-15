import type { Crop, Farm } from "./data";
import type { Pesos } from "./api";
import type { SetupInputs } from "./PropertyWizard";

/** Everything the user enters about the property, kept in the browser between visits. */
export type SavedState = {
    farm: Farm;
    setupInputs?: SetupInputs;
    /** Legacy four % sliders (water, soil, income, climate risk); `pesos` is the source of truth. */
    weights: number[];
    /** Engine weights (five criteria, 0–10) used before the setup is done; with a setup they live in setupInputs.pesos. */
    pesos?: Pesos;
    crops: Crop[];
    settings: { temperature: string };
    savedAt: string;
};

const KEY = "nativa-property-v1";

/** Reads the saved property, or null when nothing was saved (or storage is blocked/corrupt). */
export function loadSaved(): SavedState | null {
    try {
        const raw = localStorage.getItem(KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw) as SavedState;
        return parsed && parsed.farm ? parsed : null;
    } catch {
        return null;
    }
}

/** Saves the property and returns the save time, or null when the browser refuses storage (the app keeps working in memory). */
export function persist(state: Omit<SavedState, "savedAt">): string | null {
    const savedAt = new Date().toISOString();
    try {
        localStorage.setItem(KEY, JSON.stringify({ ...state, savedAt }));
        return savedAt;
    } catch {
        return null;
    }
}

export function clearSaved(): void {
    try {
        localStorage.removeItem(KEY);
    } catch {
        /* Storage is optional. */
    }
}
