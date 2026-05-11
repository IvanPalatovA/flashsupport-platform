import { describe, expect, test } from "vitest";

import { asOperatorAction, asString, asUserRole } from "../../src/models";

describe("models", () => {
  test("validates role and action", () => {
    expect(asUserRole("operator", "role")).toBe("operator");
    expect(asOperatorAction("close_chat", "action")).toBe("close_chat");
  });

  test("throws for invalid string", () => {
    expect(() => asString("", "text", 1, 10)).toThrow();
  });
});
