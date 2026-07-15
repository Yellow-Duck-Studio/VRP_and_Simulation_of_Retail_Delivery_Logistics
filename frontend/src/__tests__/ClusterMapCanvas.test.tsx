import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ClusterMapCanvas from '../components/ClusterMapCanvas';
import * as api from '../api';

// ─── Mock the API module ───────────────────────
vi.mock('../api');
const mockedApi = vi.mocked(api);

// ─── Real timers for animation intervals ──────
beforeEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();

  mockedApi.getOrder.mockImplementation((_taskId, orderId) => {
    if (orderId === 1) {
      return {
        id: 1,
        lat: 55.75,
        lon: 37.62,
        warehouseId: 10,
        pickupReadyAt: '2023-01-01T10:00:00Z',
        deliveryDeadlineAt: '2023-01-01T12:00:00Z',
        weight: 5,
        taskId: 0,
        createdAt: '2023-01-01T08:00:00Z',
      };
    }
    return undefined;
  });
  mockedApi.getOrdersForTask.mockReturnValue([
    {
      id: 1,
      lat: 55.75,
      lon: 37.62,
      warehouseId: 10,
      pickupReadyAt: '2023-01-01T10:00:00Z',
      deliveryDeadlineAt: '2023-01-01T12:00:00Z',
      weight: 5,
      taskId: 0,
      createdAt: '2023-01-01T08:00:00Z',
    },
  ]);
  mockedApi.getWarehousesForTask.mockReturnValue([
    {
      id: 10,
      lat: 55.76,
      lon: 37.61,
      taskId: 0,
    },
  ]);

  mockedApi.loadOrdersDataset.mockResolvedValue(undefined);
  mockedApi.loadWarehousesDataset.mockResolvedValue(undefined);
});

// ─── Helper to wait for data loading to finish ──
const waitForDataLoaded = async () => {
  await waitFor(() => {
    expect(mockedApi.loadOrdersDataset).toHaveBeenCalled();
    expect(mockedApi.loadWarehousesDataset).toHaveBeenCalled();
  });
  await act(() => Promise.resolve());
};

// ═══════════════════════════════════════════════
describe('ClusterMapCanvas – idle / running states', () => {
  it('shows idle animation when no clusters and not running', async () => {
    render(<ClusterMapCanvas clusters={[]} taskId="0" dataset="small" />);
    await waitForDataLoaded();

    expect(screen.getByText(/Idle Fleet Mileage/)).toBeInTheDocument();
  });

  it('shows running animation when isRunning is true', async () => {
    render(<ClusterMapCanvas clusters={[]} taskId="0" dataset="small" isRunning />);
    await waitForDataLoaded();

    expect(screen.getByText(/Clusterization in progress/)).toBeInTheDocument();
  });
});

// ═══════════════════════════════════════════════
describe('ClusterMapCanvas – with clusters', () => {
  it('renders order points and warehouses', async () => {
    const cluster = { order_ids: [1], order_sequence: null };
    render(<ClusterMapCanvas clusters={[cluster]} taskId="0" dataset="small" />);
    await waitForDataLoaded();

    await waitFor(() => {
      expect(screen.getByText('1')).toBeInTheDocument();
    });

    expect(screen.getByText('W10')).toBeInTheDocument();
  });

  it('shows tooltip on order hover', async () => {
    const cluster = { order_ids: [1], order_sequence: null };
    render(<ClusterMapCanvas clusters={[cluster]} taskId="0" dataset="small" />);
    await waitForDataLoaded();

    await waitFor(() => screen.getByText('1'));

    const pointLabel = screen.getByText('1');
    const pointGroup = pointLabel.closest('g')!;

    fireEvent.mouseEnter(pointGroup);

    await waitFor(() => {
      expect(screen.getByText('Order #1')).toBeInTheDocument();
      expect(screen.getByText('Mass:')).toBeInTheDocument();
      expect(screen.getByText('5 kg')).toBeInTheDocument();
    });
  });

  it('shows warehouse tooltip on hover', async () => {
    const cluster = { order_ids: [1], order_sequence: null };
    render(<ClusterMapCanvas clusters={[cluster]} taskId="0" dataset="small" />);
    await waitForDataLoaded();

    await waitFor(() => screen.getByText('W10'));

    const warehouseGroup = screen.getByText('W10').closest('g')!;
    fireEvent.mouseEnter(warehouseGroup);

    await waitFor(() => {
      expect(screen.getByText('Warehouse #10')).toBeInTheDocument();
      expect(screen.getByText('1 order assigned')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════════
describe('ClusterMapCanvas – zoom controls', () => {
  it('has zoom in, zoom out, and reset buttons', async () => {
    const cluster = { order_ids: [1], order_sequence: null };
    render(<ClusterMapCanvas clusters={[cluster]} taskId="0" dataset="small" />);
    await waitForDataLoaded();
    await waitFor(() => screen.getByText('1'));

    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(3);
  });

  it('changes transform scale when zoom in is clicked', async () => {
    const cluster = { order_ids: [1], order_sequence: null };
    render(<ClusterMapCanvas clusters={[cluster]} taskId="0" dataset="small" />);
    await waitForDataLoaded();
    await waitFor(() => screen.getByText('1'));

    const zoomInBtn = screen.getAllByRole('button')[0];
    const svg = document.querySelector('svg')!;
    const g = svg.querySelector('g')!;

    expect(g.getAttribute('transform')).toContain('scale(1)');

    fireEvent.click(zoomInBtn);

    await waitFor(() => {
      expect(g.getAttribute('transform')).toContain('scale(1.2)');
    });
  });
});