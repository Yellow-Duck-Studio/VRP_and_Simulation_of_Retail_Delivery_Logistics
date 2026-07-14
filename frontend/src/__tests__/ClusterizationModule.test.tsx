import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ClusterProgressEvent, AllResults } from '../api';
import * as api from '../api';
import { MockWebSocket } from '../__mocks__/websocket';
import ClusterizationModule from '../components/ClusterizationModule';

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
    let resolveClustering: (value: AllResults) => void = () => {};
    const clusteringPromise = new Promise<AllResults>((resolve) => {
      resolveClustering = resolve;
    });

    mockedApi.runClusteringWithProgress.mockImplementation(
      (_algorithms: string[], _dataset: string, onEvent: (e: ClusterProgressEvent) => void) => {
        onEvent({ type: 'algo_start', algorithm: 'GNN' });
        onEvent({ type: 'log', algorithm: 'GNN', line: 'Loading data...' });
        onEvent({ type: 'algo_done', algorithm: 'GNN', data: [
          {
            task_id: '1',
            warehouse_id: '1',
            num_orders: 2,
            clusters: [
              {
                order_ids: ['1'],
                feasible: true,
                transport: 'bike',
                order_sequence: ['1'],
                distance_km: 0.5,
                duration_min: 2,
                cost: 10.0,
              },
              {
                order_ids: ['2'],
                feasible: true,
                transport: 'bike',
                order_sequence: ['2'],
                distance_km: 0.7,
                duration_min: 3,
                cost: 15.0,
              },
            ],
          },
        ] });
        onEvent({ type: 'done' });
        return clusteringPromise;
      }
    );

    render(<ClusterizationModule />);
    await selectAlgorithm('GNN');

    await clickRun();

    expect(screen.getByRole('button', { name: /run/i })).toBeDisabled();

    setTimeout(() => resolveClustering({}), 0);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /run/i })).toBeEnabled();
    });

    expect(screen.getByText('Loading data...')).toBeInTheDocument();
  });

  it('shows alert on clustering failure', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    mockedApi.runClusteringWithProgress.mockRejectedValue(new Error('Something broke'));

    render(<ClusterizationModule />);
    await selectAlgorithm('DBScan');
    await clickRun();

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Clustering failed: Error: Something broke');
    });

    alertSpy.mockRestore();
  });
});