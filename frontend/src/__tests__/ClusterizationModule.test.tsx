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
    expect(screen.getByText('Algorithms')).toBeInTheDocument();
    for (const algo of ['DBScan', 'Clarke Wright', 'Sweep', 'Destroy & Repair', 'Random']) {
      expect(screen.getByLabelText(algo)).toBeInTheDocument();
    }
    expect(screen.getByRole('button', { name: /run/i })).toBeDisabled();
  });

  it('enables Run button when at least one algorithm is selected', async () => {
    render(<ClusterizationModule />);
    await selectAlgorithm('DBScan');
    expect(screen.getByRole('button', { name: /run/i })).toBeEnabled();
  });

  it('calls runClusteringWithProgress and displays progress logs', async () => {
    mockedApi.runClusteringWithProgress.mockImplementation(
      (_algorithms: string[], onEvent: (e: ClusterProgressEvent) => void) =>
        new Promise((resolve) => {
          onEvent({ type: 'algo_start', algorithm: 'DBScan' });
          onEvent({ type: 'log', algorithm: 'DBScan', line: 'Loading data...' });
          onEvent({ type: 'algo_done', algorithm: 'DBScan', data: { task_1: [[[1, 2]]] } });
          onEvent({ type: 'done' });
          setTimeout(() => resolve({}), 0);
        })
    );

    render(<ClusterizationModule />);
    await selectAlgorithm('DBScan');

    // Fire click synchronously – does NOT wait for the async handler to finish
    fireEvent.click(screen.getByRole('button', { name: /run/i }));

    // Now the loading state should be visible (spinner is in the DOM)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument();

    // Wait for the logs to appear (after the mock resolves)
    await waitFor(() => {
      expect(screen.getByText('Loading data...')).toBeInTheDocument();
    });

    // Polygon / variant controls appear
    await waitFor(() => {
      expect(screen.getByText('Polygon')).toBeInTheDocument();
      expect(screen.getByText('Variant')).toBeInTheDocument();
    });

    // Run button is no longer disabled
    expect(screen.getByRole('button', { name: /run/i })).not.toBeDisabled();
  });

  it('updates displayed clusters when polygon / variant change', async () => {
    mockedApi.runClusteringWithProgress.mockImplementation(
      (_algorithms: string[], onEvent: (e: ClusterProgressEvent) => void) =>
        new Promise((resolve) => {
          onEvent({
            type: 'algo_done',
            algorithm: 'DBScan',
            data: {
              task_1: [[[1]], [[2]]],  // 2 variants for task 1
              task_2: [[[3]], [[4]]],  // 2 variants for task 2
            },
          });
          onEvent({ type: 'done' });
          resolve({});
        })
    );

    render(<ClusterizationModule />);
    await selectAlgorithm('DBScan');
    await clickRun();

    // Wait for controls
    await waitFor(() => screen.getByDisplayValue('1')); // polygon input = 1

    // Default: last variant of task_1 → variant index 1 = [[2]]
    const canvas = screen.getByTestId('cluster-map-canvas');
    const clusters = JSON.parse(canvas.dataset.clusters!);
    expect(clusters).toEqual([[2]]);

    // Switch to polygon 2
    const polyInput = screen.getAllByRole('spinbutton')[0]; // first = polygon
    fireEvent.change(polyInput, { target: { value: '2' } });

    // Variant resets to last variant of task_2 = [[4]]
    await waitFor(() => {
      const c = screen.getByTestId('cluster-map-canvas');
      const cl = JSON.parse(c.dataset.clusters!);
      expect(cl).toEqual([[4]]);
    });

    // Switch variant to 1
    const varInput = screen.getAllByRole('spinbutton')[1]; // second = variant
    fireEvent.change(varInput, { target: { value: '1' } });

    // Now shows first variant of task_2 = [[3]]
    await waitFor(() => {
      const c = screen.getByTestId('cluster-map-canvas');
      const cl = JSON.parse(c.dataset.clusters!);
      expect(cl).toEqual([[3]]);
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