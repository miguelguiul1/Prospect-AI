export interface NewSearchState {
  status: "idle" | "error";
  message?: string;
}

export const INITIAL_STATE: NewSearchState = { status: "idle" };
