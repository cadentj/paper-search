import { create } from "zustand";

interface UiState {
  selectedRunId?: string;
  selectedPaperId?: string;
  selectedIdeaClaimId?: string;
  selectedIdeaWarrantId?: string;
  setSelectedRunId: (id?: string) => void;
  setSelectedPaperId: (id?: string) => void;
  setSelectedIdeaClaimId: (id?: string) => void;
  setSelectedIdeaWarrantId: (id?: string) => void;
}

export const useUiStore = create<UiState>((set) => ({
  selectedRunId: undefined,
  selectedPaperId: undefined,
  selectedIdeaClaimId: undefined,
  selectedIdeaWarrantId: undefined,
  setSelectedRunId: (id) => set({ selectedRunId: id }),
  setSelectedPaperId: (id) => set({ selectedPaperId: id }),
  setSelectedIdeaClaimId: (id) => set({ selectedIdeaClaimId: id }),
  setSelectedIdeaWarrantId: (id) => set({ selectedIdeaWarrantId: id }),
}));
