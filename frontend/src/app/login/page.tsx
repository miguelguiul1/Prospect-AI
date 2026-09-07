import Link from "next/link";
import type { Metadata } from "next";
import { Radar } from "lucide-react";
import { AuthForm } from "@/components/auth/auth-form";
import { loginAction } from "@/lib/auth/actions";

export const metadata: Metadata = { title: "Entrar" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <span className="flex size-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Radar aria-hidden className="size-5" />
          </span>
          <h1 className="font-heading text-lg font-semibold text-foreground">Entrar no Prospect AI</h1>
          <p className="text-sm text-muted-foreground">Acesse sua conta para ver o CRM e os prospects.</p>
        </div>

        <AuthForm mode="login" action={loginAction} nextPath={next} />

        <p className="text-center text-sm text-muted-foreground">
          Ainda não tem conta?{" "}
          <Link href="/register" className="font-medium text-primary hover:underline">
            Criar conta
          </Link>
        </p>
      </div>
    </div>
  );
}
