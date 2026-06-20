import packageInfo from "../package.json";
import ClusterizationModule from "./components/ClusterizationModule";
import SimulationModule from "./components/SimulationModule";

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50 py-6 px-4 sm:px-6 lg:px-8">
      <header className="max-w-7xl mx-auto mb-8 flex items-center justify-between">
        <div className="flex items-center gap-1">
          <img className="h-16 scale-150 origin-center" src="/duck.png" alt=""></img>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
            VRP Testbench <span className="text-black-500">v{packageInfo.version}</span>
          </h1>
        </div>
      </header>

      <main className="max-w-7xl mx-auto space-y-6">
        <ClusterizationModule />
        <SimulationModule />
      </main>
    </div>
  );
}