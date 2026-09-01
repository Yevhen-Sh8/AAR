/**
 * The Order #440 generators shipped on the API and «Налаштування» listed them
 * as available, but no screen ever linked to them: the only way to obtain an
 * act was to hand-craft an HTTP request. These tests hold the page to the two
 * things that make it usable — events identified by serial number, and no
 * button that produces a 400.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setSession } from "../lib/auth";
import Mod440Page from "./Mod440Page";

const EVENTS = [
  {
    id: 11, client_event_id: null, event_date: "2025-12-01", outcome: "lost",
    item_serial_no: "FPV-00042", item_type_code: "FPV-7", operator_code: "3-БрОП",
    loss_reason_code: "reb", repair_reason_code: null, notes: null,
    aborted: false, abort_reason: null, recorded_at: "2025-12-01T10:00:00",
  },
  {
    // No reason code → the generator answers 400, so it must not be offered.
    id: 12, client_event_id: null, event_date: "2025-12-02", outcome: "lost",
    item_serial_no: "FPV-00043", item_type_code: "FPV-7", operator_code: "3-БрОП",
    loss_reason_code: null, repair_reason_code: null, notes: null,
    aborted: false, abort_reason: null, recorded_at: "2025-12-02T10:00:00",
  },
];

let requested: string[] = [];

beforeEach(() => {
  requested = [];
  setSession("tok", "a@b.c");
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:x"),
    revokeObjectURL: vi.fn(),
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      requested.push(String(url));
      if (String(url).includes("/events")) {
        const outcome = String(url).includes("outcome=repair") ? "repair" : "lost";
        return new Response(
          JSON.stringify(EVENTS.filter((e) => e.outcome === outcome)),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("binary", { status: 200 });
    }),
  );
});

afterEach(() => vi.restoreAllMocks());

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Mod440Page />
    </QueryClientProvider>,
  );
}

describe("Order #440 forms", () => {
  it("identifies an event by its serial number, not a row id", async () => {
    mount();
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /FPV-00042/ })).toBeDefined();
    });
  });

  it("does not offer an event that cannot produce a document", async () => {
    mount();
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /FPV-00042/ })).toBeDefined();
    });
    // id 12 has no loss reason; the API would refuse it with 400.
    expect(screen.queryByRole("option", { name: /FPV-00043/ })).toBeNull();
  });

  it("keeps the act button inert until an event is chosen", async () => {
    mount();
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /FPV-00042/ })).toBeDefined();
    });
    const buttons = screen.getAllByRole("button", { name: /DOCX/ }) as HTMLButtonElement[];
    expect(buttons.every((b) => b.disabled)).toBe(true);
  });

  it("passes the unit name into the generated inventory sheet", async () => {
    mount();
    const unit = screen.getByPlaceholderText("в/ч А0000");
    fireEvent.change(unit, { target: { value: "в/ч А1234" } });

    fireEvent.click(screen.getAllByRole("button", { name: /XLSX/ })[0]);

    await waitFor(() => {
      expect(
        requested.some(
          (u) => u.includes("inventory.xlsx") && u.includes(encodeURIComponent("в/ч А1234")),
        ),
      ).toBe(true);
    });
  });

  it("builds an act request once an event is picked", async () => {
    mount();
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /FPV-00042/ })).toBeDefined();
    });
    const pickers = screen.getAllByRole("combobox") as HTMLSelectElement[];
    fireEvent.change(pickers[0], { target: { value: "11" } });

    const docx = screen.getAllByRole("button", { name: /DOCX/ })[0] as HTMLButtonElement;
    expect(docx.disabled).toBe(false);
    fireEvent.click(docx);

    await waitFor(() => {
      expect(requested.some((u) => u.includes("/loss-act/11.docx"))).toBe(true);
    });
  });
});
