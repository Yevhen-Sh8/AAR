/**
 * The form must write against the dictionaries the admin actually maintains.
 *
 * It used to hardcode item types `A` / `B` and take the operator as free text.
 * A unit whose real codes were anything else could not file an event through
 * the UI at all — the server rejected the code, and before the queue fix the
 * event then disappeared without trace.
 */
import "fake-indexeddb/auto";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import EventForm from "./EventForm";

const DICTS: Record<string, unknown> = {
  "/dictionaries/item-types": [
    { id: 1, code: "FPV-7", name_uk: "Ударний FPV" },
    { id: 2, code: "RECON-2", name_uk: "Розвідувальний" },
  ],
  "/dictionaries/operators": [{ id: 1, code: "3-БрОП", name_uk: "3 бригада" }],
  "/dictionaries/loss-reasons": [
    { id: 1, code: "reb", name_uk: "Придушення РЕБ", zone: "external" },
  ],
  "/dictionaries/repair-reasons": [
    { id: 1, code: "mech", name_uk: "Механічне пошкодження", zone: "operator" },
  ],
};

function mountWith(fetchImpl: typeof fetch) {
  vi.stubGlobal("fetch", fetchImpl);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <EventForm />
    </QueryClientProvider>,
  );
}

const servingDicts: typeof fetch = (async (url: string) => {
  const key = Object.keys(DICTS).find((k) => String(url).includes(k));
  return new Response(JSON.stringify(key ? DICTS[key] : []), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}) as unknown as typeof fetch;

afterEach(() => vi.restoreAllMocks());

describe("event form", () => {
  it("offers the item types and operators from the dictionaries", async () => {
    mountWith(servingDicts);

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /FPV-7/ })).toBeDefined();
    });
    expect(screen.getByRole("option", { name: /RECON-2/ })).toBeDefined();
    expect(screen.getByRole("option", { name: /3-БрОП/ })).toBeDefined();

    // The old hardcoded pair must be gone, not merely joined by the real codes.
    expect(screen.queryByRole("option", { name: "A" })).toBeNull();
    expect(screen.queryByRole("option", { name: "B" })).toBeNull();
  });

  it("says so when a dictionary cannot be read, instead of an empty dropdown", async () => {
    const failing: typeof fetch = (async () =>
      new Response("nope", { status: 500 })) as unknown as typeof fetch;
    mountWith(failing);

    await waitFor(() => {
      expect(screen.getAllByText(/довідник недоступний/i).length).toBeGreaterThan(0);
    });
    // Submitting is blocked while there is nothing valid to submit.
    const submit = screen.getByRole("button", { name: "Подати" }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
  });

  it("says so when a dictionary is empty", async () => {
    const empty: typeof fetch = (async () =>
      new Response("[]", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })) as unknown as typeof fetch;
    mountWith(empty);

    await waitFor(() => {
      expect(screen.getAllByText(/довідник порожній/i).length).toBeGreaterThan(0);
    });
  });

  it("can express a launch that was aborted before takeoff", async () => {
    // `aborted` is what separates the two success denominators. Until now it
    // could only arrive by import, so the UI could not produce the honest one.
    mountWith(servingDicts);
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /FPV-7/ })).toBeDefined();
    });
    expect(screen.getByLabelText(/Зрив до запуску/)).toBeDefined();
  });

  it("labels outcomes in Ukrainian", async () => {
    mountWith(servingDicts);
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Успіх/ })).toBeDefined();
    });
    expect(screen.getByRole("option", { name: /Втрата/ })).toBeDefined();
    expect(screen.queryByRole("option", { name: "Success" })).toBeNull();
  });
});
