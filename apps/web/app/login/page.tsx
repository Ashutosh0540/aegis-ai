"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Field } from "@/components/field";
import { api, ApiError } from "@/lib/api-client";

const schema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});

type FormValues = z.infer<typeof schema>;

export default function LoginPage() {
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit(values: FormValues) {
    setServerError(null);
    try {
      await api.login(values.email, values.password);
      router.push("/dashboard");
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : "Something went wrong");
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={handleSubmit(onSubmit)}
        className="w-full max-w-sm rounded-2xl border border-border bg-background p-8 shadow-lg"
      >
        <h1 className="mb-1 text-xl font-semibold">Welcome back</h1>
        <p className="mb-6 text-sm text-foreground/60">Sign in to your AegisAI workspace.</p>

        <div className="flex flex-col gap-4">
          <Field label="Email" type="email" placeholder="you@company.com" {...register("email")} error={errors.email?.message} />
          <Field label="Password" type="password" placeholder="••••••••" {...register("password")} error={errors.password?.message} />
        </div>

        {serverError && <p className="mt-4 text-sm text-red-400">{serverError}</p>}

        <button
          type="submit"
          disabled={isSubmitting}
          className="mt-6 w-full rounded-lg bg-primary py-2.5 font-medium text-background hover:opacity-90 disabled:opacity-50"
        >
          {isSubmitting ? "Signing in…" : "Sign in"}
        </button>

        <p className="mt-4 text-center text-sm text-foreground/60">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="text-primary hover:underline">
            Create one
          </Link>
        </p>
      </form>
    </main>
  );
}
