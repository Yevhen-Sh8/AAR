import { describe, it, expect } from "vitest";
import { errMessage, functionLabel, operatorLabel } from "./people";
import mockPeople from "../../public/mock/people.json";

describe("people labels", () => {
  it("renders a missing function as «не вказано», never blank", () => {
    expect(functionLabel(null)).toBe("не вказано");
    expect(functionLabel(undefined)).toBe("не вказано");
    expect(functionLabel("crew")).toBe("екіпаж");
    expect(functionLabel("manufacturer")).toBe("представник виробника");
  });

  it("maps operator_id to the operator code", () => {
    const ops = [{ id: 7, code: "E-07", name_uk: "Експлуатант 07" }];
    expect(operatorLabel(7, ops)).toBe("E-07");
    expect(operatorLabel(null, ops)).toBe("—");
    expect(operatorLabel(9, ops)).toBe("#9");
  });

  it("surfaces the API 409 detail", () => {
    expect(errMessage(new Error('API 409: {"detail":"Особа використовується"}'))).toBe(
      "Особа використовується",
    );
  });
});

describe("demo roster", () => {
  it("contains people outside the demo case operator (the flexible pick)", () => {
    const caseOperatorId = 7; // mock/cases.json case #27
    const offRoster = mockPeople.filter((p) => p.operator_id !== caseOperatorId);
    expect(offRoster.length).toBeGreaterThan(0);
    // and someone with no affiliation at all is still pickable
    expect(mockPeople.some((p) => p.operator_id === null)).toBe(true);
  });
});
