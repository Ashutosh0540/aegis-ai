"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError, clearTokens, Organization, User } from "@/lib/api-client";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [newOrgName, setNewOrgName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.me(), api.listOrganizations()])
      .then(([userResult, orgsResult]) => {
        setUser(userResult);
        setOrgs(orgsResult);
      })
      .catch(() => router.push("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  function signOut() {
    clearTokens();
    router.push("/login");
  }

  async function createOrganization(e: React.FormEvent) {
    e.preventDefault();
    if (!newOrgName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const org = await api.createOrganization(newOrgName.trim());
      setOrgs((prev) => [...prev, org]);
      setNewOrgName("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create organization");
    } finally {
      setCreating(false);
    }
  }

  if (loading) {
    return <main className="flex min-h-screen items-center justify-center">Loading…</main>;
  }

  return (
    <main className="min-h-screen px-6 py-8">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">AegisAI</h1>
          <p className="text-sm text-foreground/60">Enterprise AI Operations</p>
        </div>
        <button
          onClick={signOut}
          className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-muted/20"
        >
          Sign out
        </button>
      </header>

      <section className="mb-6 rounded-2xl border border-border p-6">
        <h2 className="mb-2 text-base font-medium">Welcome, {user?.full_name}</h2>
        <p className="text-sm text-foreground/60">
          Your account ({user?.email}) is authenticated and ready.
        </p>
      </section>

      <section className="mb-6 rounded-2xl border border-border p-6">
        <h2 className="mb-3 text-sm font-medium">Your organizations</h2>
        {orgs.length === 0 ? (
          <p className="mb-4 text-sm text-foreground/60">
            You don&apos;t belong to an organization yet — create one to get started.
          </p>
        ) : (
          <ul className="mb-4 flex flex-col gap-2">
            {orgs.map((org) => (
              <li
                key={org.id}
                className="flex items-center justify-between rounded-lg border border-border px-4 py-2 text-sm"
              >
                <span>{org.name}</span>
                <div className="flex gap-4">
                  <Link href="/dashboard/documents" className="text-primary hover:underline">
                    Documents →
                  </Link>
                  <Link href="/dashboard/chat" className="text-primary hover:underline">
                    Chat →
                  </Link>
                  <Link href="/dashboard/tickets" className="text-primary hover:underline">
                    Tickets →
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}

        <form onSubmit={createOrganization} className="flex gap-2">
          <input
            value={newOrgName}
            onChange={(e) => setNewOrgName(e.target.value)}
            placeholder="New organization name"
            className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none ring-primary/50 focus:ring-2"
          />
          <button
            type="submit"
            disabled={creating}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-background hover:opacity-90 disabled:opacity-50"
          >
            {creating ? "Creating…" : "Create"}
          </button>
        </form>
        {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
      </section>

      <section className="rounded-2xl border border-border p-6">
        <h2 className="mb-2 text-base font-medium">What&apos;s next</h2>
        <p className="text-sm text-foreground/60">
          AI chat with your documents is live — try it from the{" "}
          <Link href="/dashboard/chat" className="text-primary hover:underline">
            chat page
          </Link>
          . Multi-step agents, workflows, and analytics land in upcoming milestones.
        </p>
      </section>
    </main>
  );
}

