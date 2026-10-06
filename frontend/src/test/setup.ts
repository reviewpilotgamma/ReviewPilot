import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Node 24's undici Request rejects jsdom's AbortSignal (different realm). Drop the
// signal on failure so react-router data-router navigations still work in tests.
const OriginalRequest = globalThis.Request;
globalThis.Request = class Request extends OriginalRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    try {
      super(input, init);
    } catch (error) {
      if (init?.signal && error instanceof TypeError) {
        const { signal: _signal, ...rest } = init;
        super(input, rest);
        return;
      }
      throw error;
    }
  }
} as typeof OriginalRequest;

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});
