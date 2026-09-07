"use server";

import { redirect } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { login as loginRequest, register as registerRequest } from "@/lib/api/auth";
import { clearSessionToken, setSessionToken } from "@/lib/auth/session";
import type { ActionState } from "@/lib/action-types";

function toActionState(error: unknown): ActionState {
  if (error instanceof ApiError) {
    return { status: "error", message: error.message };
  }
  console.error("[auth-actions] erro inesperado:", error);
  return { status: "error", message: "Ocorreu um erro inesperado. Tente novamente." };
}

function redirectTarget(formData: FormData): string {
  const next = formData.get("next");
  return typeof next === "string" && next.startsWith("/") ? next : "/dashboard";
}

export async function loginAction(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");

  let token: string;
  try {
    token = (await loginRequest(email, password)).access_token;
  } catch (error) {
    return toActionState(error);
  }

  await setSessionToken(token);
  redirect(redirectTarget(formData));
}

export async function registerAction(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const email = String(formData.get("email") ?? "");
  const name = String(formData.get("name") ?? "");
  const password = String(formData.get("password") ?? "");

  let token: string;
  try {
    token = (await registerRequest(email, name, password)).access_token;
  } catch (error) {
    return toActionState(error);
  }

  await setSessionToken(token);
  redirect("/dashboard");
}

export async function logoutAction(): Promise<void> {
  await clearSessionToken();
  redirect("/login");
}
