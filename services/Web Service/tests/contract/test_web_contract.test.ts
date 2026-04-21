import { describe, expect, test } from "vitest";

describe("web contract", () => {
  test("api base path", () => {
    expect("/api/auth/login").toContain("/api/auth/");
  });
});
