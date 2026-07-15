"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api, ApiError, Organization, Ticket, ticketsApi } from "@/lib/api-client";

const STATUS_STYLES: Record<Ticket["status"], string> = {
  open: "bg-yellow-500/15 text-yellow-400",
  in_progress: "bg-blue-500/15 text-blue-400",
  resolved: "bg-green-500/15 text-green-400",
  closed: "bg-muted/30 text-foreground/50",
};

const PRIORITY_STYLES: Record<Ticket["priority"], string> = {
  low: "text-foreground/50",
  medium: "text-foreground/70",
  high: "text-orange-400",
  urgent: "text-red-400",
};

export default function TicketsPage() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<Ticket["priority"]>("medium");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadTickets = useCallback(async (orgId: string) => {
    setTickets(await ticketsApi.list(orgId));
  }, []);

  useEffect(() => {
    api.listOrganizations().then((result) => {
      setOrgs(result);
      if (result.length > 0) setSelectedOrgId(result[0].id);
    });
  }, []);

  useEffect(() => {
    if (selectedOrgId) loadTickets(selectedOrgId);
  }, [selectedOrgId, loadTickets]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedOrgId || !title.trim() || !description.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await ticketsApi.create(selectedOrgId, title.trim(), description.trim(), priority);
      setTitle("");
      setDescription("");
      setPriority("medium");
      await loadTickets(selectedOrgId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create ticket");
    } finally {
      setCreating(false);
    }
  }

  async function handleStatusChange(ticketId: string, status: Ticket["status"]) {
    if (!selectedOrgId) return;
    await ticketsApi.update(selectedOrgId, ticketId, { status });
    await loadTickets(selectedOrgId);
  }

  return (
    <main className="min-h-screen px-6 py-8">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <Link href="/dashboard" className="text-sm text-foreground/60 hover:underline">
            ← Dashboard
          </Link>
          <h1 className="mt-1 text-lg font-semibold">Tickets</h1>
        </div>

        {orgs.length > 1 && (
          <select
            value={selectedOrgId ?? ""}
            onChange={(e) => setSelectedOrgId(e.target.value)}
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
          >
            {orgs.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name}
              </option>
            ))}
          </select>
        )}
      </header>

      {orgs.length === 0 ? (
        <p className="text-sm text-foreground/60">
          You don&apos;t belong to an organization yet — create one from the dashboard first.
        </p>
      ) : (
        <>
          <form
            onSubmit={handleCreate}
            className="mb-6 flex flex-col gap-3 rounded-2xl border border-border p-6"
          >
            <h2 className="text-sm font-medium">New ticket</h2>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Title"
              className="rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none ring-primary/50 focus:ring-2"
            />
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Description"
              rows={3}
              className="rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none ring-primary/50 focus:ring-2"
            />
            <div className="flex items-center gap-3">
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as Ticket["priority"])}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </select>
              <button
                type="submit"
                disabled={creating}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-background hover:opacity-90 disabled:opacity-50"
              >
                {creating ? "Creating…" : "Create ticket"}
              </button>
            </div>
            {error && <p className="text-xs text-red-400">{error}</p>}
          </form>

          <div className="overflow-hidden rounded-2xl border border-border">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-muted/10 text-left text-xs uppercase text-foreground/50">
                <tr>
                  <th className="px-4 py-3">Title</th>
                  <th className="px-4 py-3">Priority</th>
                  <th className="px-4 py-3">Source</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {tickets.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-4 py-6 text-center text-foreground/50">
                      No tickets yet.
                    </td>
                  </tr>
                )}
                {tickets.map((t) => (
                  <tr key={t.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3">
                      <div className="font-medium">{t.title}</div>
                      <div className="text-xs text-foreground/50">{t.description}</div>
                    </td>
                    <td className={`px-4 py-3 capitalize ${PRIORITY_STYLES[t.priority]}`}>
                      {t.priority}
                    </td>
                    <td className="px-4 py-3 text-foreground/50">
                      {t.source === "agent" ? "🤖 Agent" : "Manual"}
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={t.status}
                        onChange={(e) => handleStatusChange(t.id, e.target.value as Ticket["status"])}
                        className={`rounded-full border-0 px-2.5 py-1 text-xs font-medium ${STATUS_STYLES[t.status]}`}
                      >
                        <option value="open">Open</option>
                        <option value="in_progress">In progress</option>
                        <option value="resolved">Resolved</option>
                        <option value="closed">Closed</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </main>
  );
}
