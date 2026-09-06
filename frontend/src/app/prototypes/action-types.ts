export interface PrototypeActionState {
  status: "idle" | "error";
  message?: string;
}

export const INITIAL_STATE: PrototypeActionState = { status: "idle" };
