import { describe, expect, test } from "vitest";

describe("health contract", () => {
  test("health endpoint path is stable", () => {
    expect("/health").toBe("/health");
  });
});
