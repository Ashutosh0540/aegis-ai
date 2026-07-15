"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, documentsApi, DocumentSummary, Organization } from "@/lib/api-client";

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-yellow-500/15 text-yellow-400",
  processing: "bg-blue-500/15 text-blue-400",
  completed: "bg-green-500/15 text-green-400",
  failed: "bg-red-500/15 text-red-400",
  needs_ocr: "bg-orange-500/15 text-orange-400",
};

function StatusBadge({ status }: { status?: string }) {
  if (!status) return null;
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[status] ?? "bg-muted/30"}`}>
      {status.replace("_", " ")}
    </span>
  );
}

export default function DocumentsPage() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [statusById, setStatusById] = useState<Record<string, string>>({});
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadDocuments = useCallback(async (orgId: string) => {
    const docs = await documentsApi.list(orgId);
    setDocuments(docs);
    // Fetch latest status for each doc so newly-processed uploads update live.
    const details = await Promise.all(docs.map((d) => documentsApi.get(orgId, d.id)));
    const next: Record<string, string> = {};
    details.forEach((d) => {
      if (d.latest_version) next[d.id] = d.latest_version.status;
    });
    setStatusById(next);
  }, []);

  useEffect(() => {
    api.listOrganizations().then((result) => {
      setOrgs(result);
      if (result.length > 0) setSelectedOrgId(result[0].id);
    });
  }, []);

  useEffect(() => {
    if (selectedOrgId) loadDocuments(selectedOrgId);
  }, [selectedOrgId, loadDocuments]);

  // Poll while any document is still pending/processing.
  useEffect(() => {
    if (!selectedOrgId) return;
    const hasInFlight = Object.values(statusById).some(
      (s) => s === "pending" || s === "processing"
    );
    if (!hasInFlight) return;
    const interval = setInterval(() => loadDocuments(selectedOrgId), 2000);
    return () => clearInterval(interval);
  }, [selectedOrgId, statusById, loadDocuments]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !selectedOrgId) return;
    setUploading(true);
    setError(null);
    try {
      await documentsApi.upload(selectedOrgId, file);
      await loadDocuments(selectedOrgId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleDelete(documentId: string) {
    if (!selectedOrgId) return;
    await documentsApi.remove(selectedOrgId, documentId);
    await loadDocuments(selectedOrgId);
  }

  return (
    <main className="min-h-screen px-6 py-8">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <Link href="/dashboard" className="text-sm text-foreground/60 hover:underline">
            ← Dashboard
          </Link>
          <h1 className="mt-1 text-lg font-semibold">Knowledge base</h1>
        </div>

        {orgs.length > 0 && (
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
          <div className="mb-6 rounded-2xl border border-border p-6">
            <h2 className="mb-2 text-sm font-medium">Upload a document</h2>
            <p className="mb-4 text-xs text-foreground/60">PDF, DOCX, Markdown, or TXT — up to 25 MB.</p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.md,.txt"
              onChange={handleUpload}
              disabled={uploading}
              className="text-sm file:mr-4 file:rounded-lg file:border-0 file:bg-primary file:px-4 file:py-2 file:text-sm file:font-medium file:text-background hover:file:opacity-90"
            />
            {uploading && <p className="mt-2 text-xs text-foreground/60">Uploading…</p>}
            {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
          </div>

          <div className="overflow-hidden rounded-2xl border border-border">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-muted/10 text-left text-xs uppercase text-foreground/50">
                <tr>
                  <th className="px-4 py-3">Filename</th>
                  <th className="px-4 py-3">Version</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {documents.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-4 py-6 text-center text-foreground/50">
                      No documents yet.
                    </td>
                  </tr>
                )}
                {documents.map((doc) => (
                  <tr key={doc.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3">{doc.filename}</td>
                    <td className="px-4 py-3 text-foreground/60">v{doc.latest_version_number}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={statusById[doc.id]} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleDelete(doc.id)}
                        className="text-xs text-red-400 hover:underline"
                      >
                        Delete
                      </button>
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
