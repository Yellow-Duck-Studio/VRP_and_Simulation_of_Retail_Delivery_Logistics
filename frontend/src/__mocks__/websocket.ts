import { vi } from 'vitest';

/**
 * A controllable mock of the browser WebSocket class for Vitest.
 *
 * Usage in test setup:
 *   const mockWs = new MockWebSocket('ws://localhost:3001/ws/cluster');
 *   vi.stubGlobal('WebSocket', vi.fn(() => mockWs));
 *
 * Then trigger events:
 *   mockWs.simulateOpen();
 *   mockWs.simulateMessage({ type: 'algo_start', algorithm: 'DBScan' });
 *   mockWs.simulateError();
 *   mockWs.simulateClose();
 */
export class MockWebSocket {
  // Event handlers exactly like the browser WebSocket
  onopen: ((this: WebSocket, ev: Event) => unknown) | null = null;
  onmessage: ((this: WebSocket, ev: MessageEvent) => unknown) | null = null;
  onerror: ((this: WebSocket, ev: Event) => unknown) | null = null;
  onclose: ((this: WebSocket, ev: CloseEvent) => unknown) | null = null;

  // Mocked methods
  send = vi.fn();
  close = vi.fn();

  // Required but unused static constants (prevents runtime errors if code references them)
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  constructor(public url: string) {}

  // ── Simulation helpers ──────────────────────
  simulateOpen() {
    this.onopen?.call(this as unknown as WebSocket, new Event('open'));
  }

  simulateMessage(data: unknown) {
    this.onmessage?.call(
      this as unknown as WebSocket,
      new MessageEvent('message', { data: JSON.stringify(data) })
    );
  }

  simulateError() {
    this.onerror?.call(this as unknown as WebSocket, new Event('error'));
  }

  simulateClose(eventInit?: CloseEventInit) {
    this.onclose?.call(this as unknown as WebSocket, new CloseEvent('close', eventInit));
  }
}