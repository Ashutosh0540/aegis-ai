"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, chatApi, ChatMessage, Conversation, Organization } from "@/lib/api-client";

function CitationList({ citations }: { citations: ChatMessage["citations"] }) {
  if (citations.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {citations.map((c) => (
        <span
          key={c.chunk_id}
          title={`chunk #${c.chunk_index} · score ${c.score.toFixed(2)}`}
          className="rounded-full border border-border px-2 py-0.5 text-xs text-foreground/60"
        >
          📄 {c.filename}
        </span>
      ))}
    </div>
  );
}

export default function ChatPage() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.listOrganizations().then((result) => {
      setOrgs(result);
      if (result.length > 0) setSelectedOrgId(result[0].id);
    });
  }, []);

  const loadConversations = useCallback(async (orgId: string) => {
    const convs = await chatApi.listConversations(orgId);
    setConversations(convs);
    if (convs.length > 0) setActiveConversationId((prev) => prev ?? convs[0].id);
  }, []);

  useEffect(() => {
    if (selectedOrgId) loadConversations(selectedOrgId);
  }, [selectedOrgId, loadConversations]);

  useEffect(() => {
    if (selectedOrgId && activeConversationId) {
      chatApi.listMessages(selectedOrgId, activeConversationId).then(setMessages);
    } else {
      setMessages([]);
    }
  }, [selectedOrgId, activeConversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function startNewConversation() {
    if (!selectedOrgId) return;
    const conv = await chatApi.createConversation(selectedOrgId);
    setConversations((prev) => [conv, ...prev]);
    setActiveConversationId(conv.id);
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedOrgId || !input.trim()) return;

    let conversationId = activeConversationId;
    if (!conversationId) {
      const conv = await chatApi.createConversation(selectedOrgId);
      setConversations((prev) => [conv, ...prev]);
      conversationId = conv.id;
      setActiveConversationId(conversationId);
    }

    const question = input.trim();
    setInput("");
    setSending(true);
    // Optimistically show the user's message while waiting for the reply.
    setMessages((prev) => [
      ...prev,
      {
        id: `optimistic-${Date.now()}`,
        conversation_id: conversationId!,
        role: "user",
        content: question,
        citations: [],
        created_at: new Date().toISOString(),
      },
    ]);

    try {
      await chatApi.sendMessage(selectedOrgId, conversationId, question);
      const refreshed = await chatApi.listMessages(selectedOrgId, conversationId);
      setMessages(refreshed);
    } finally {
      setSending(false);
    }
  }

  return (
    <main className="flex min-h-screen">
      <aside className="w-64 shrink-0 border-r border-border p-4">
        <Link href="/dashboard" className="mb-4 block text-sm text-foreground/60 hover:underline">
          ← Dashboard
        </Link>

        {orgs.length > 1 && (
          <select
            value={selectedOrgId ?? ""}
            onChange={(e) => {
              setSelectedOrgId(e.target.value);
              setActiveConversationId(null);
            }}
            className="mb-3 w-full rounded-lg border border-border bg-background px-2 py-1.5 text-sm"
          >
            {orgs.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name}
              </option>
            ))}
          </select>
        )}

        <button
          onClick={startNewConversation}
          className="mb-4 w-full rounded-lg bg-primary py-2 text-sm font-medium text-background hover:opacity-90"
        >
          + New conversation
        </button>

        <ul className="flex flex-col gap-1">
          {conversations.map((conv) => (
            <li key={conv.id}>
              <button
                onClick={() => setActiveConversationId(conv.id)}
                className={`w-full truncate rounded-lg px-3 py-2 text-left text-sm ${
                  conv.id === activeConversationId ? "bg-muted/30" : "hover:bg-muted/10"
                }`}
              >
                {conv.title ?? "Untitled conversation"}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="flex flex-1 flex-col">
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {messages.length === 0 && (
            <p className="text-sm text-foreground/50">
              Ask a question about your organization&apos;s documents — answers cite the
              source chunks they&apos;re drawn from.
            </p>
          )}
          <div className="flex flex-col gap-4">
            {messages.map((m) => (
              <div key={m.id} className={m.role === "user" ? "self-end text-right" : "self-start"}>
                <div
                  className={`inline-block max-w-lg rounded-2xl px-4 py-2.5 text-sm ${
                    m.role === "user" ? "bg-primary text-background" : "border border-border"
                  }`}
                >
                  {m.content}
                </div>
                {m.role === "assistant" && <CitationList citations={m.citations} />}
              </div>
            ))}
          </div>
          <div ref={bottomRef} />
        </div>

        <form onSubmit={handleSend} className="flex gap-2 border-t border-border p-4">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your documents…"
            disabled={sending}
            className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none ring-primary/50 focus:ring-2"
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-background hover:opacity-90 disabled:opacity-50"
          >
            {sending ? "Thinking…" : "Send"}
          </button>
        </form>
      </section>
    </main>
  );
}
