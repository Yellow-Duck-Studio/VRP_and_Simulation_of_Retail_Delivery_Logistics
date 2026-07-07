import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import { expect, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import SimulationModule from '../components/SimulationModule';
import * as api from '../api';

vi.mock('../api');
const mockedApi = vi.mocked(api);

test('renders Run button and empty output', () => {
  render(<SimulationModule />);
  expect(screen.getByText(/Press Run to start simulation/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Run/i })).toBeEnabled();
});

test('calls runSimulation and displays formatted output', async () => {
  mockedApi.runSimulation.mockImplementationOnce(
    () =>
      new Promise<string>((resolve) => {
        setTimeout(() => resolve('=== Results ===\n  metric: 42\n  time: 10s'), 0);
      })
  );

  render(<SimulationModule />);

  fireEvent.click(screen.getByRole('button', { name: /Run/i }));

  expect(document.querySelector('.animate-spin')).toBeInTheDocument();

  await waitFor(() => {
    expect(screen.getByText('=== Results ===')).toBeInTheDocument();
  });

  expect(screen.getByRole('button', { name: /Run/i })).not.toBeDisabled();
});

test('displays error message when simulation fails', async () => {
  mockedApi.runSimulation.mockRejectedValueOnce(new Error('Server down'));

  render(<SimulationModule />);
  await userEvent.click(screen.getByRole('button', { name: /Run/i }));

  await waitFor(() => {
    expect(screen.getByText(/Simulation failed:/)).toBeInTheDocument();
    expect(screen.getByText(/Server down/)).toBeInTheDocument();
  });
});