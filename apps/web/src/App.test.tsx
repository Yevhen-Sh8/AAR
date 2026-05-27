import "fake-indexeddb/auto";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import App from "./App";

vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("[]", { status: 200 }))));

describe("App", () => {
  it("renders sidebar logo", () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getAllByText("AAR").length).toBeGreaterThan(0);
  });
});
