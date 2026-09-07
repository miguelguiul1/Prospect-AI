import Link from "next/link";
import type { Metadata } from "next";
import { Radar } from "lucide-react";
import { AuthForm } from "@/components/auth/auth-form";
import { registerAction } from "@/lib/auth/actions";

export const metadata: Metadata = { title: "Criar conta" };

export default function RegisterPage() {
  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <span className="flex size-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Radar aria-hidden className="size-5" />
          </span>
          <h1 className="font-heading text-lg font-semibold text-foreground">Criar conta</h1>
          <p className="text-sm text-muted-foreground">
            Necessário para ter suas próprias oportunidades no CRM.
          </p>
        </div>

        <AuthForm mode="register" action={registerAction} />

        <p className="text-center text-sm text-muted-foreground">
          Já tem conta?{" "}
          <Link href="/login" className="font-medium text-primary hover:underline">
            Entrar
          </Link>
        </p>
      </div>
    </div>
  );
}
