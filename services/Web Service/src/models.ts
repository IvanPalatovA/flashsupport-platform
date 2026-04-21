import { OperatorAction, UserRole } from "./domain";

export function asString(value: unknown, fieldName: string, minLength = 1, maxLength = 5000): string {
  if (typeof value !== "string") {
    throw new Error(`${fieldName} must be a string`);
  }

  const normalized = value.trim();
  if (normalized.length < minLength) {
    throw new Error(`${fieldName} must be at least ${minLength} characters long`);
  }
  if (normalized.length > maxLength) {
    throw new Error(`${fieldName} must be at most ${maxLength} characters long`);
  }

  return normalized;
}

export function asOptionalString(value: unknown, fieldName: string, maxLength = 5000): string | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  return asString(value, fieldName, 1, maxLength);
}

export function asPositiveInt(value: unknown, fieldName: string, defaultValue: number, minValue = 1, maxValue = 50): number {
  if (value === undefined || value === null || value === "") {
    return defaultValue;
  }

  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < minValue || parsed > maxValue) {
    throw new Error(`${fieldName} must be an integer in range [${minValue}, ${maxValue}]`);
  }

  return parsed;
}

export function asBoolean(value: unknown, fieldName: string): boolean {
  if (typeof value !== "boolean") {
    throw new Error(`${fieldName} must be a boolean`);
  }
  return value;
}

export function asUserRole(value: unknown, fieldName: string): UserRole {
  if (value !== "registered_user" && value !== "operator" && value !== "admin") {
    throw new Error(`${fieldName} must be one of: registered_user, operator, admin`);
  }
  return value;
}

export function asOperatorAction(value: unknown, fieldName: string): OperatorAction {
  if (
    value !== "close_chat" &&
    value !== "block_chat" &&
    value !== "resolve_chat" &&
    value !== "send_to_specialist_queue"
  ) {
    throw new Error(`${fieldName} must be one of: close_chat, block_chat, resolve_chat, send_to_specialist_queue`);
  }
  return value;
}
