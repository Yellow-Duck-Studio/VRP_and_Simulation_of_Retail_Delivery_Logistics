import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock Heroicons
vi.mock('@heroicons/react/24/solid', () => ({
  PlayIcon: () => <div data-testid="play-icon" />,
}));

vi.mock('@heroicons/react/24/outline', () => ({
  MapIcon: () => <div data-testid="map-icon" />,
  PlusIcon: () => <div data-testid="plus-icon" />,
  MinusIcon: () => <div data-testid="minus-icon" />,
}));