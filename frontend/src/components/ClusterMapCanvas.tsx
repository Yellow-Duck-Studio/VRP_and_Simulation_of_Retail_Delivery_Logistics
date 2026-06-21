import {useState, useMemo, useCallback, useRef, useEffect, useId} from "react";
import { orders, loadOrdersDataset, DATA_BASE_URL, type OrderInfo } from "../api.ts";
import {
  PlusIcon,
  MinusIcon,
  MapIcon,
} from '@heroicons/react/24/outline';

interface ClusterMapProps {
  clusters: number[][];
}

interface Point {
  id: number;
  x: number;
  y: number;
  clusterIdx: number;
  orderIdxInCluster: number;
}

const COLORS = [
  "#3b82f6", "#ef4444", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899",
  "#06b6d4", "#84cc16", "#f97316", "#6366f1", "#14b8a6", "#e11d48",
  "#0ea5e9", "#a855f7", "#f43f5e", "#22c55e", "#eab308", "#3b82f6",
  "#8b5cf6", "#f97316", "#06b6d4", "#84cc16", "#ec4899", "#6366f1"
];

const BASE_POINT_RADIUS = 8;
const VIEW_BOX_WIDTH = 800;
const VIEW_BOX_HEIGHT = 600;
const PADDING = 50;

function shortenLine(
  x1: number, y1: number,
  x2: number, y2: number,
  offsetStart: number,
  offsetEnd: number
) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len === 0) return { x1, y1, x2, y2 };
  const ux = dx / len;
  const uy = dy / len;
  return {
    x1: x1 + ux * offsetStart,
    y1: y1 + uy * offsetStart,
    x2: x2 - ux * offsetEnd,
    y2: y2 - uy * offsetEnd,
  };
}

const formatTime = (isoString: string) => {
  if (!isoString) return "N/A";
  try {
    return new Date(isoString).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return isoString;
  }
};

export default function ClusterMap({ clusters }: ClusterMapProps) {
  const [dataLoaded, setDataLoaded] = useState(false);
  const [virtualDistance, setVirtualDistance] = useState(0);
  const [hoveredPoint, setHoveredPoint] = useState<Point | null>(null);
  const [tooltipOrder, setTooltipOrder] = useState<OrderInfo | null>(null);
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({});

  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 });

  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const isDragging = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });
  const transformStart = useRef({ x: 0, y: 0 });

  const arrowId = useId();

  useEffect(() => {
    if (Object.keys(orders).length === 0) {
      loadOrdersDataset(`${DATA_BASE_URL}/data/orders.csv`).finally(() => setDataLoaded(true));
    } else {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDataLoaded(true);
    }
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setVirtualDistance(prev => prev + Math.floor(Math.random() * 5) + 2);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const positions = useMemo(() => {
    const posMap = new Map<number, { x: number, y: number }>();
    const validOrders = Object.values(orders).filter(
      o => typeof o.lat === 'number' && !isNaN(o.lat) && typeof o.lon === 'number' && !isNaN(o.lon)
    );

    if (validOrders.length === 0) return posMap;

    const minLat = Math.min(...validOrders.map(o => o.lat));
    const maxLat = Math.max(...validOrders.map(o => o.lat));
    const minLon = Math.min(...validOrders.map(o => o.lon));
    const maxLon = Math.max(...validOrders.map(o => o.lon));

    const avgLat = (minLat + maxLat) / 2;
    const lonCorrection = Math.cos(avgLat * (Math.PI / 180));

    const correctedMinLon = minLon * lonCorrection;
    const correctedMaxLon = maxLon * lonCorrection;

    let lonRange = correctedMaxLon - correctedMinLon;
    let latRange = maxLat - minLat;
    if (lonRange < 0.00001) lonRange = 0.01;
    if (latRange < 0.00001) latRange = 0.01;

    const usableWidth = VIEW_BOX_WIDTH - PADDING * 2;
    const usableHeight = VIEW_BOX_HEIGHT - PADDING * 2;

    const scale = Math.min(usableWidth / lonRange, usableHeight / latRange);

    const xOffset = (VIEW_BOX_WIDTH - lonRange * scale) / 2;
    const yOffset = (VIEW_BOX_HEIGHT - latRange * scale) / 2;

    const coordCounts = new Map<string, number>();

    validOrders.forEach(o => {
      const cLon = o.lon * lonCorrection;
      let x = xOffset + (cLon - correctedMinLon) * scale;
      let y = yOffset + (maxLat - o.lat) * scale;

      const coordKey = `${o.lat.toFixed(4)}_${o.lon.toFixed(4)}`;
      const count = coordCounts.get(coordKey) || 0;

      if (count > 0) {
        const angle = count * 137.5 * (Math.PI / 180);
        const radius = BASE_POINT_RADIUS + (count * 2);
        x += Math.cos(angle) * radius;
        y += Math.sin(angle) * radius;
      }

      coordCounts.set(coordKey, count + 1);
      posMap.set(o.id, { x, y });
    });

    return posMap;
  }, [dataLoaded]);

  const points: Point[] = useMemo(() => {
    const result: Point[] = [];
    let fallbackSpiralIdx = 0;

    clusters.forEach((cluster, ci) => {
      cluster.forEach((rawId, orderIdx) => {
        const id = Number(rawId);
        const pos = positions.get(id);

        if (pos && !isNaN(pos.x) && !isNaN(pos.y)) {
          result.push({ id, x: pos.x, y: pos.y, clusterIdx: ci, orderIdxInCluster: orderIdx });
        } else {
          const r = 25 * Math.sqrt(fallbackSpiralIdx + 1);
          const theta = fallbackSpiralIdx * 137.508 * (Math.PI / 180);
          const x = VIEW_BOX_WIDTH / 2 + r * Math.cos(theta);
          const y = VIEW_BOX_HEIGHT / 2 + r * Math.sin(theta);

          result.push({ id, x, y, clusterIdx: ci, orderIdxInCluster: orderIdx });
          fallbackSpiralIdx++;
        }
      });
    });
    return result;
  }, [clusters, positions]);

  const pointMap = useMemo(() => {
    const map = new Map<number, Point>();
    points.forEach((p) => map.set(p.id, p));
    return map;
  }, [points]);

  const hoveredClusterIdx = hoveredPoint ? hoveredPoint.clusterIdx : null;
  
  const handleMouseDown = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;
    isDragging.current = true;
    dragStart.current = { x: e.clientX, y: e.clientY };
    transformStart.current = { x: transform.x, y: transform.y };
    svgRef.current?.style.setProperty('cursor', 'grabbing');
  }, [transform]);

  const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (!isDragging.current) return;
    const dx = e.clientX - dragStart.current.x;
    const dy = e.clientY - dragStart.current.y;
    setTransform({
      ...transform,
      x: transformStart.current.x + dx,
      y: transformStart.current.y + dy,
    });
  }, [transform]);

  const handleMouseUp = useCallback(() => {
    isDragging.current = false;
    svgRef.current?.style.setProperty('cursor', 'grab');
  }, []);

  const handleMouseLeave = useCallback(() => {
    if (isDragging.current) {
      isDragging.current = false;
      svgRef.current?.style.setProperty('cursor', 'grab');
    }
  }, []);

  const handleDoubleClick = useCallback(() => {
    setTransform({ x: 0, y: 0, scale: 1 });
  }, []);


  const zoomIn = () => {
    setTransform(prev => {
      const newScale = Math.min(prev.scale * 1.2, 5);
      const centerX = VIEW_BOX_WIDTH / 2;
      const centerY = VIEW_BOX_HEIGHT / 2;
      const pointX = (centerX - prev.x) / prev.scale;
      const pointY = (centerY - prev.y) / prev.scale;
      const newX = centerX - pointX * newScale;
      const newY = centerY - pointY * newScale;
      return { x: newX, y: newY, scale: newScale };
    });
  };

  const zoomOut = () => {
    setTransform(prev => {
      const newScale = Math.max(prev.scale / 1.2, 0.5);
      const centerX = VIEW_BOX_WIDTH / 2;
      const centerY = VIEW_BOX_HEIGHT / 2;
      const pointX = (centerX - prev.x) / prev.scale;
      const pointY = (centerY - prev.y) / prev.scale;
      const newX = centerX - pointX * newScale;
      const newY = centerY - pointY * newScale;
      return { x: newX, y: newY, scale: newScale };
    });
  };

  const resetView = () => {
    setTransform({ x: 0, y: 0, scale: 1 });
  };
  

  const showTooltip = useCallback((point: Point, event: React.MouseEvent) => {
    setHoveredPoint(point);
    setTooltipOrder(orders[point.id] ?? null);

    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      let left = event.clientX - rect.left + 15;
      let top = event.clientY - rect.top + 15;

      if (left + 220 > rect.width) left = event.clientX - rect.left - 220;
      if (top + 150 > rect.height) top = event.clientY - rect.top - 150;

      setTooltipStyle({
        left: `${left}px`,
        top: `${top}px`,
        position: "absolute",
        zIndex: 10,
        pointerEvents: "none",
      });
    }
  }, []);

  const hideTooltip = useCallback(() => {
    setHoveredPoint(null);
    setTooltipOrder(null);
  }, []);

  const handlePointMouseMove = useCallback((e: React.MouseEvent) => {
    if (containerRef.current && hoveredPoint) {
      const rect = containerRef.current.getBoundingClientRect();
      let left = e.clientX - rect.left + 15;
      let top = e.clientY - rect.top + 15;
      if (left + 220 > rect.width) left = e.clientX - rect.left - 220;
      if (top + 150 > rect.height) top = e.clientY - rect.top - 150;
      setTooltipStyle(prev => ({ ...prev, left: `${left}px`, top: `${top}px` }));
    }
  }, [hoveredPoint]);


  if (!clusters || clusters.length === 0) {
    const idlePath = "M 200,300 L 300,150 L 500,150 L 600,300 L 500,450 L 300,450 Z";
    const idleCars = [
      { fill: "#3b82f6", begin: "0s" },
      { fill: "#f59e0b", begin: "-4s" },
      { fill: "#ea74e8", begin: "-8s" },
    ];
  
    return (
      <div className="relative w-full overflow-hidden border border-gray-200 rounded-lg bg-slate-50 flex items-center justify-center min-h-[400px]">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${VIEW_BOX_WIDTH} ${VIEW_BOX_HEIGHT}`}
          className="w-full h-auto max-h-[600px]"
          preserveAspectRatio="xMidYMid meet"
          style={{ cursor: 'default' }}
        >
          <g>
            <path d={idlePath} fill="none" stroke="#cbd5e1" strokeWidth="2" />
            <circle cx="200" cy="300" r="7" fill="#94a3b8" />
            <text x="200" y="300" textAnchor="middle" dominantBaseline="middle" fill="#f8fafc" fontSize="12" fontWeight="bold">5</text>
            <circle cx="300" cy="150" r="7" fill="#94a3b8" />
            <text x="300" y="150" textAnchor="middle" dominantBaseline="middle" fill="#f8fafc" fontSize="12" fontWeight="bold">9</text>
            <circle cx="500" cy="150" r="7" fill="#94a3b8" />
            <text x="500" y="150" textAnchor="middle" dominantBaseline="middle" fill="#f8fafc" fontSize="12" fontWeight="bold">3</text>
            <circle cx="600" cy="300" r="7" fill="#94a3b8" />
            <text x="600" y="300" textAnchor="middle" dominantBaseline="middle" fill="#f8fafc" fontSize="12" fontWeight="bold">2</text>
            <circle cx="500" cy="450" r="7" fill="#94a3b8" />
            <text x="500" y="450" textAnchor="middle" dominantBaseline="middle" fill="#f8fafc" fontSize="12" fontWeight="bold">7</text>
            <circle cx="300" cy="450" r="7" fill="#94a3b8" />
            <text x="300" y="450" textAnchor="middle" dominantBaseline="middle" fill="#f8fafc" fontSize="12" fontWeight="bold">1</text>
  
            {idleCars.map((car, index) => (
              <g key={index}>
                <rect x="-12" y="-7" width="24" height="14" rx="3" fill={car.fill} stroke="#ffffff" strokeWidth="1.5" />
                <rect x="1" y="-5" width="5" height="10" rx="1" fill="#1e293b" opacity="0.5" />
                <rect x="-8" y="-5" width="3" height="10" rx="1" fill="#1e293b" opacity="0.5" />
                <animateMotion dur="12s" begin={car.begin} repeatCount="indefinite" path={idlePath} rotate="auto" />
              </g>
            ))}
  
            <text x={VIEW_BOX_WIDTH / 2} y={VIEW_BOX_HEIGHT / 2} textAnchor="middle" fill="#475569" fontSize="26" fontWeight="bold">
              Idle Fleet Mileage: {virtualDistance} km
            </text>
            {!dataLoaded && (
              <text x={VIEW_BOX_WIDTH / 2} y={VIEW_BOX_HEIGHT / 2 + 30} textAnchor="middle" fill="#94a3b8" fontSize="14">
                (Loading dataset...)
              </text>
            )}
          </g>
        </svg>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="relative w-full overflow-hidden border border-gray-200 rounded-lg bg-white"
    >
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VIEW_BOX_WIDTH} ${VIEW_BOX_HEIGHT}`}
        className="w-full h-auto max-h-[600px]"
        preserveAspectRatio="xMidYMid meet"
        onMouseDown={handleMouseDown}
        onMouseMove={(e) => { handleMouseMove(e); handlePointMouseMove(e); }}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        onDoubleClick={handleDoubleClick}
        style={{ cursor: 'grab' }}
      >
        <defs>
          <marker id={arrowId} viewBox="0 0 12 12" refX="10" refY="6" markerWidth="8" markerHeight="8" orient="auto">
            <path d="M 0 0 L 12 6 L 0 12 z" fill="#6b7280" />
          </marker>
        </defs>

        <g transform={`translate(${transform.x},${transform.y}) scale(${transform.scale})`}>
          {hoveredClusterIdx !== null &&
            clusters[hoveredClusterIdx].map((idStr, i, arr) => {
              if (i === arr.length - 1) return null;
              const from = pointMap.get(Number(idStr));
              const to = pointMap.get(Number(arr[i + 1]));
              if (!from || !to) return null;

              const offset = (BASE_POINT_RADIUS + 4) / transform.scale;
              const { x1, y1, x2, y2 } = shortenLine(from.x, from.y, to.x, to.y, offset, offset);

              return (
                <line
                  key={`arrow-${from.id}-${to.id}`}
                  x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke="#6b7280" strokeWidth={1.5 / transform.scale}
                  markerEnd={`url(#${arrowId})`}
                />
              );
            })}

          {points.map((p) => {
            const isActiveCluster = hoveredClusterIdx !== null && p.clusterIdx === hoveredClusterIdx;
            const isDimmed = hoveredClusterIdx !== null && p.clusterIdx !== hoveredClusterIdx;
            const radius = BASE_POINT_RADIUS / transform.scale;

            return (
              <g
                key={p.id}
                onMouseEnter={(e) => showTooltip(p, e)}
                onMouseMove={(e) => {
                  if (containerRef.current) {
                    const rect = containerRef.current.getBoundingClientRect();
                    let left = e.clientX - rect.left + 15;
                    let top = e.clientY - rect.top + 15;
                    if (left + 220 > rect.width) left = e.clientX - rect.left - 220;
                    if (top + 150 > rect.height) top = e.clientY - rect.top - 150;
                    setTooltipStyle(prev => ({ ...prev, left: `${left}px`, top: `${top}px` }));
                  }
                }}
                onMouseLeave={hideTooltip}
                style={{ cursor: "pointer" }}
              >
                <circle
                  cx={p.x} cy={p.y} r={radius}
                  fill={COLORS[p.clusterIdx % COLORS.length]}
                  opacity={isDimmed ? 0.25 : 1}
                  stroke={isActiveCluster ? "#374151" : "none"}
                  strokeWidth={2 / transform.scale}
                />
                <text
                  x={p.x} y={p.y + (3.5 / transform.scale)}
                  textAnchor="middle" fill="white"
                  fontSize={9 / transform.scale} fontWeight="bold"
                  style={{ pointerEvents: "none", userSelect: "none" }}
                >
                  {p.id}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      <div className="absolute bottom-4 right-4 flex flex-col gap-2">
        <button
          onClick={zoomIn}
          className="bg-white shadow-md p-2 rounded-full hover:bg-gray-50 transition-colors"
        >
          <PlusIcon className="w-6 h-6 text-gray-700" />
        </button>

        <button
          onClick={zoomOut}
          className="bg-white shadow-md p-2 rounded-full hover:bg-gray-50 transition-colors"
        >
          <MinusIcon className="w-6 h-6 text-gray-700" />
        </button>

        <button
          onClick={resetView}
          className="bg-white shadow-md p-2 rounded-full hover:bg-gray-50 transition-colors"
        >
          <MapIcon className="w-6 h-6 text-gray-700" />
        </button>
      </div>

      {hoveredPoint && (
        <div
          className="bg-white border border-gray-300 rounded-lg shadow-xl p-3 text-sm w-[210px]"
          style={tooltipStyle}
        >
          <div className="font-semibold text-gray-800 border-b border-gray-200 pb-1 mb-2">
            Order #{hoveredPoint.id}
            {tooltipOrder && <span className="text-gray-400 text-xs font-normal ml-2">WH: {tooltipOrder.warehouseId}</span>}
          </div>
          {tooltipOrder ? (
            <div className="text-gray-600 space-y-1.5 text-xs">
              <div className="flex justify-between"><span className="font-medium">Mass:</span> <span>{tooltipOrder.weight} kg</span></div>
              <div className="flex justify-between"><span className="font-medium">Pickup:</span> <span>{formatTime(tooltipOrder.pickupReadyAt)}</span></div>
              <div className="flex justify-between text-red-600"><span className="font-medium">Deadline:</span> <span>{formatTime(tooltipOrder.deliveryDeadlineAt)}</span></div>
              <div className="pt-1 mt-1 border-t border-gray-100 text-[10px] text-gray-400 text-center">
                {tooltipOrder.lat?.toFixed(4)}, {tooltipOrder.lon?.toFixed(4)}
              </div>
            </div>
          ) : (
            <div className="text-gray-500 text-xs text-center py-2">
              Geodata for this Order ID is undefined. Check path if is wrong
            </div>
          )}
        </div>
      )}
    </div>
  );
}