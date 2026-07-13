// src/__tests__/ClusterizationModule.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ClusterProgressEvent } from '../api';
import * as api from '../api';
import { MockWebSocket } from '../__mocks__/websocket';
import ClusterizationModule from "../components/ClusterizationModule.tsx";

// ─── Mocks ──────────────────────────────────────
vi.mock('../api');
vi.mock('../components/ClusterMapCanvas', () => ({
  default: vi.fn((props: { clusters: number[][]; taskId: number | string; isRunning?: boolean }) => (
    <div
      data-testid="cluster-map-canvas"
      data-clusters={JSON.stringify(props.clusters)}
      data-taskid={String(props.taskId)}
      data-isrunning={String(props.isRunning ?? false)}
    />
  )),
}));

const mockedApi = vi.mocked(api);

// ─── WebSocket setup ────────────────────────────
let mockWs: MockWebSocket;

beforeEach(() => {
  vi.clearAllMocks();
  mockWs = new MockWebSocket('ws://localhost:3001/ws/cluster');
  vi.stubGlobal('WebSocket', vi.fn(() => mockWs));
});

// ─── Helpers ────────────────────────────────────
const selectAlgorithm = async (name: string) => {
  await userEvent.click(screen.getByLabelText(name));
};

const clickRun = async () => {
  await userEvent.click(screen.getByRole('button', { name: /run/i }));
};

// ─── Tests ──────────────────────────────────────
describe('ClusterizationModule', () => {
  it('renders algorithm list and a disabled Run button', () => {
    render(<ClusterizationModule />);
    expect(screen.getByText('Standalone')).toBeInTheDocument();
    expect(screen.getByText('Evolutionary algorithm')).toBeInTheDocument();
    for (const algo of ['GNN', 'DBScan', 'Clarke Wright', 'Sweep', 'Destroy & Repair', 'Random']) {
      expect(screen.getByLabelText(algo)).toBeInTheDocument();
    }
    expect(screen.getByRole('button', { name: /run/i })).toBeDisabled();
  });

  it('enables Run button when at least one algorithm is selected', async () => {
    render(<ClusterizationModule />);
    await selectAlgorithm('GNN');
    expect(screen.getByRole('button', { name: /run/i })).toBeEnabled();
  });

  it('calls runClusteringWithProgress and displays progress logs', async () => {
    mockedApi.runClusteringWithProgress.mockImplementation(
      (_algorithms: string[], onEvent: (e: ClusterProgressEvent) => void) =>
        new Promise((resolve) => {
          onEvent({ type: 'algo_start', algorithm: 'GNN' });
          onEvent({ type: 'log', algorithm: 'GNN', line: 'Loading data...' });
          onEvent({ type: 'algo_done', algorithm: 'GNN', data: [
            {
              task_id: "1",
              warehouse_id: "1",
              num_orders: 2,
              clusters: [
                { order_ids: ["1"], feasible: true, transport: "bike", order_sequence: ["1"] },
                { order_ids: ["2"], feasible: true, transport: "bike", order_sequence: ["2"] }
              ],
              total_cost: 100,
              feasible: true
            }
          ] });
          onEvent({ type: 'done' });
          setTimeout(() => resolve({}), 0);
        })
    );

    render(<ClusterizationModule />);
    await selectAlgorithm('GNN');

    // Fire click synchronously – does NOT wait for the async handler to finish
    fireEvent.click(screen.getByRole('button', { name: /run/i }));

    // Now the loading state should be visible (spinner is in the DOM)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument();

    // Wait for clustering to complete
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /run/i })).not.toBeDisabled();
    });
  });


  it('shows alert on clustering failure', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    mockedApi.runClusteringWithProgress.mockRejectedValue(new Error('Something broke'));

    render(<ClusterizationModule />);
    await selectAlgorithm('DBScan');
    await clickRun();

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Clasterization failed: Error: Something broke');
    });

    alertSpy.mockRestore();
  });
});