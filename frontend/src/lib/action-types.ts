export interface ActionState {
  status: "idle" | "success" | "error";
  message?: string;
}

export const INITIAL_STATE: ActionState = { status: "idle" };
