import Link from "next/link";

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 px-4 text-center">
      <span className="rounded-full border border-border px-3 py-1 text-xs uppercase tracking-widest text-muted">
        Enterprise AI Operations
      </span>
      <h1 className="max-w-2xl text-4xl font-semibold tracking-tight sm:text-5xl">
        Secure AI-powered enterprise workflow automation.
      </h1>
      <p className="max-w-xl text-base text-foreground/70">
        AegisAI unifies your knowledge base, AI agents, and workflow automation into one
        governed, auditable platform.
      </p>
      <div className="flex gap-4">
        <Link
          href="/register"
          className="rounded-lg bg-primary px-5 py-2.5 font-medium text-background hover:opacity-90"
        >
          Get started
        </Link>
        <Link
          href="/login"
          className="rounded-lg border border-border px-5 py-2.5 font-medium hover:bg-muted/20"
        >
          Sign in
        </Link>
      </div>
    </main>
  );
}
