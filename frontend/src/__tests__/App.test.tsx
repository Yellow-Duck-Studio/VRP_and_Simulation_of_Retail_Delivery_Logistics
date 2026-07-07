import { render } from '@testing-library/react';
import App from '../App';

vi.mock('../components/ClusterizationModule', () => ({
  default: () => <div>Clusterization Module Mock</div>,
}));

vi.mock('../components/SimulationModule', () => ({
  default: () => <div>Simulation Module Mock</div>,
}));

test('renders header and modules', () => {
  const { getByText } = render(<App />);
  expect(getByText(/VRP Testbench/)).toBeInTheDocument();
  expect(getByText('Clusterization Module Mock')).toBeInTheDocument();
  expect(getByText('Simulation Module Mock')).toBeInTheDocument();
});