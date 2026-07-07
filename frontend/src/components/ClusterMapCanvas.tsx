import React, {useCallback, useEffect, useId, useMemo, useRef, useState} from "react";
import {
  DATA_BASE_URL,
  getOrder,
  getOrdersForTask,
  getWarehousesForTask,
  loadOrdersDataset,
  loadWarehousesDataset,
  type OrderInfo,
  orders,
  warehouses
} from "../api.ts";
import {MapIcon, MinusIcon, PlusIcon,} from '@heroicons/react/24/outline';

export interface ClusterMapProps {
  clusters: number[][];
  taskId: number | string;
  isRunning?: boolean;
}

interface Point {
  id: number;
  x: number;
  y: number;
  clusterIdx: number;
  orderIdxInCluster: number;
}

interface WarehousePoint {
  id: number;
  x: number;
  y: number;
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

export default function ClusterMap({ clusters, taskId, isRunning = false }: ClusterMapProps) {
  const [dataLoaded, setDataLoaded] = useState(false);
  const [virtualDistance, setVirtualDistance] = useState(0);
  const [hoveredPoint, setHoveredPoint] = useState<Point | null>(null);
  const [tooltipOrder, setTooltipOrder] = useState<OrderInfo | null>(null);
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({});
  const [hoveredWarehouse, setHoveredWarehouse] = useState<WarehousePoint | null>(null);
  const [warehouseTooltipStyle, setWarehouseTooltipStyle] = useState<React.CSSProperties>({});

  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 });

  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const isDragging = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });
  const transformStart = useRef({ x: 0, y: 0 });

  const arrowId = useId();

  useEffect(() => {
    const loadAll = async () => {
      const promises: Promise<void>[] = [];
      if (Object.keys(orders).length === 0) {
        promises.push(loadOrdersDataset(`${DATA_BASE_URL}/data/orders.csv`));
      }
      if (Object.keys(warehouses).length === 0) {
        promises.push(loadWarehousesDataset(`${DATA_BASE_URL}/data/warehouses.csv`));
      }
      if (promises.length > 0) {
        await Promise.all(promises);
      }
      setDataLoaded(true);
    };
    loadAll();
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setVirtualDistance(prev => prev + Math.floor(Math.random() * 5) + 2);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const { positions, warehousePoints } = useMemo(() => {
    const posMap = new Map<number, { x: number, y: number }>();
    const validOrders = getOrdersForTask(taskId).filter(
      o => typeof o.lat === 'number' && !isNaN(o.lat) && typeof o.lon === 'number' && !isNaN(o.lon)
    );

    if (validOrders.length === 0) return { positions: posMap, warehousePoints: [] as WarehousePoint[] };

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

    const project = (lat: number, lon: number) => {
      const cLon = lon * lonCorrection;
      const x = xOffset + (cLon - correctedMinLon) * scale;
      const y = yOffset + (maxLat - lat) * scale;
      return { x, y };
    };

    const coordCounts = new Map<string, number>();

    validOrders.forEach(o => {
      let { x, y } = project(o.lat, o.lon);

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

    const whPoints: WarehousePoint[] = getWarehousesForTask(taskId)
      .filter(w => typeof w.lat === 'number' && !isNaN(w.lat) && typeof w.lon === 'number' && !isNaN(w.lon))
      .map(w => ({ id: w.id, ...project(w.lat, w.lon) }));

    return { positions: posMap, warehousePoints: whPoints };
  }, [taskId]);

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

  // Orders belonging to the hovered warehouse
  const warehouseHighlightedOrderIds = useMemo(() => {
    if (!hoveredWarehouse) return null;
    const taskOrders = getOrdersForTask(taskId);
    return new Set(taskOrders.filter(o => o.warehouseId === hoveredWarehouse.id).map(o => o.id));
  }, [hoveredWarehouse, taskId]);

  // Warehouse id to highlight when hovering an order
  const highlightedWarehouseId = useMemo(() => {
    if (!hoveredPoint) return null;
    const order = getOrder(taskId, hoveredPoint.id);
    return order ? order.warehouseId : null;
  }, [hoveredPoint, taskId]);

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
    setTooltipOrder(getOrder(taskId, point.id) ?? null);

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
  }, [taskId]);

  const hideTooltip = useCallback(() => {
    setHoveredPoint(null);
    setTooltipOrder(null);
  }, []);

  const showWarehouseTooltip = useCallback((wp: WarehousePoint, event: React.MouseEvent) => {
    setHoveredWarehouse(wp);
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      let left = event.clientX - rect.left + 15;
      let top = event.clientY - rect.top + 15;
      if (left + 180 > rect.width) left = event.clientX - rect.left - 180;
      if (top + 80 > rect.height) top = event.clientY - rect.top - 80;
      setWarehouseTooltipStyle({
        left: `${left}px`,
        top: `${top}px`,
        position: "absolute",
        zIndex: 10,
        pointerEvents: "none",
      });
    }
  }, []);

  const hideWarehouseTooltip = useCallback(() => {
    setHoveredWarehouse(null);
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
    if (isRunning) {
      return (
        <div className="relative w-full overflow-hidden border border-gray-200 rounded-lg bg-slate-50 flex items-center justify-center min-h-[400px]">
          <svg
            viewBox={`0 0 ${VIEW_BOX_WIDTH} ${VIEW_BOX_HEIGHT}`}
            className="w-full h-auto max-h-[600px]"
            preserveAspectRatio="xMidYMid meet"
          >
            <style>{`
              @keyframes slideLoop {
                0% { transform: translateX(850px); opacity: 0; }
                8.33% { transform: translateX(400px); opacity: 1; }
                33.33% { transform: translateX(400px); opacity: 1; }
                41.66% { transform: translateX(-100px); opacity: 0; }
                100% { transform: translateX(-100px); opacity: 0; }
              }
              .runner-anim { animation: slideLoop 6s ease-in-out infinite; opacity: 0; }
              .moped-anim { animation: slideLoop 6s ease-in-out infinite; animation-delay: 2s; opacity: 0; }
              .car-anim { animation: slideLoop 6s ease-in-out infinite; animation-delay: 4s; opacity: 0; }
            `}</style>

            {/* Road */}
            <line x1="0" y1="372" x2={VIEW_BOX_WIDTH} y2="372" stroke="#e2e8f0" strokeWidth="2" />

            {/* Runner */}
            <g className="runner-anim">
              <g transform="translate(0, 372)">
                <g>
                  <animateTransform attributeName="transform" type="translate" values="0,-4; 0,-8; 0,-4" dur="0.4s" repeatCount="indefinite" />

                  <rect x="-23" y="-70" width="16" height="20" rx="3" fill="#64748b" stroke="#334155" strokeWidth="2" />
                  <line x1="-15" y1="-70" x2="-15" y2="-50" stroke="#334155" strokeWidth="2"/>

                  <g>
                    <animateTransform attributeName="transform" type="rotate" values="30 0 -65; -30 0 -65; 30 0 -65" dur="0.4s" repeatCount="indefinite" />
                    <line x1="0" y1="-65" x2="10" y2="-35" stroke="#94a3b8" strokeWidth="9" strokeLinecap="round" />
                  </g>
                  <g>
                    <animateTransform attributeName="transform" type="rotate" values="-40 0 -30; 40 0 -30; -40 0 -30" dur="0.4s" repeatCount="indefinite" />
                    <line x1="0" y1="-30" x2="-10" y2="4" stroke="#94a3b8" strokeWidth="11" strokeLinecap="round" />
                  </g>

                  <path d="M 0,-65 C 5,-50 -2,-35 0,-30" stroke="#94a3b8" strokeWidth="12" strokeLinecap="round" fill="none" />

                  <g>
                    <animateTransform attributeName="transform" type="rotate" values="40 0 -30; -40 0 -30; 40 0 -30" dur="0.4s" repeatCount="indefinite" />
                    <line x1="0" y1="-30" x2="15" y2="4" stroke="#94a3b8" strokeWidth="11" strokeLinecap="round" />
                  </g>
                  <g>
                    <animateTransform attributeName="transform" type="rotate" values="-30 0 -65; 30 0 -65; -30 0 -65" dur="0.4s" repeatCount="indefinite" />
                    <line x1="0" y1="-65" x2="-12" y2="-35" stroke="#94a3b8" strokeWidth="9" strokeLinecap="round" />
                  </g>

                  <circle cx="2" cy="-80" r="9" fill="#94a3b8" stroke="#94a3b8" strokeWidth="2" />
                </g>
              </g>
            </g>

            {/* Moped */}
            <g className="moped-anim">
              <g transform="translate(0, 372)">
                <g>
                  <animateTransform attributeName="transform" type="translate" values="0,0; 0,-2; 0,0" dur="0.3s" repeatCount="indefinite" />

                  <path d="M -35,-20 L -15,-20 L 10,-40 L 35,-40 Q 40,-40 40,-35 L 25,-20 L 10,-20" fill="#334155" />
                  <path d="M 10,-40 C 0,-40 -10,-20 -15,-20" fill="none" stroke="#334155" strokeWidth="6" strokeLinecap="round" />
                  <line x1="38" y1="-39" x2="30" y2="-48" stroke="#334155" strokeWidth="4" strokeLinecap="round" />

                  {/* BAG */}
                  <g transform="rotate(45 90 75)">
                    <rect x="-82" y="50" width="16" height="20" rx="2" fill="#64748b" stroke="#334155" strokeWidth="2" />
                    <line x1="-75" y1="50" x2="-75" y2="70" stroke="#334155" strokeWidth="2" />
                  </g>

                  {/* Courier */}
                  <path d="M 4 -49 Q -5 -43 -16 -29" stroke="#94a3b8" strokeWidth="10" strokeLinecap="round" fill="none" />
                  <circle cx="11" cy="-58" r="9" fill="#94a3b8" stroke="#94a3b8" strokeWidth="2" />
                  <line x1="-1" y1="-47" x2="25" y2="-40" stroke="#94a3b8" strokeWidth="5" strokeLinecap="round" />
                  {/* legs */}
                  <line x1="-16" y1="-29" x2="5" y2="-29" stroke="#94a3b8" strokeWidth="8" strokeLinecap="round" />
                  <line x1="5" y1="-29" x2="-3" y2="-10" stroke="#94a3b8" strokeWidth="8" strokeLinecap="round" />
                </g>

                <g transform="translate(-25, -12)">
                  <circle cx="0" cy="0" r="12" fill="#1e293b" />
                  <circle cx="0" cy="0" r="6" fill="#94a3b8" />
                  <g>
                    <animateTransform attributeName="transform" type="rotate" values="0; 360" dur="0.4s" repeatCount="indefinite" />
                    <line x1="0" y1="-6" x2="0" y2="6" stroke="#cbd5e1" strokeWidth="2" />
                    <line x1="-6" y1="0" x2="6" y2="0" stroke="#cbd5e1" strokeWidth="2" />
                  </g>
                </g>
                <g transform="translate(25, -12)">
                  <circle cx="0" cy="0" r="12" fill="#1e293b" />
                  <circle cx="0" cy="0" r="6" fill="#94a3b8" />
                  <g>
                    <animateTransform attributeName="transform" type="rotate" values="0; 360" dur="0.4s" repeatCount="indefinite" />
                    <line x1="0" y1="-6" x2="0" y2="6" stroke="#cbd5e1" strokeWidth="2" />
                    <line x1="-6" y1="0" x2="6" y2="0" stroke="#cbd5e1" strokeWidth="2" />
                  </g>
                </g>
              </g>
            </g>

            {/* Car */}
            <g className="car-anim">
              <g transform="translate(0, 372)">
                <g>
                  <animateTransform attributeName="transform" type="translate" values="0,0; 0,-2; 0,0" dur="0.5s" repeatCount="indefinite" />

                  <path d="M -45,-15 L 45,-15 L 45,-25 C 45,-30 40,-35 30,-35 L 20,-35 L 10,-45 C 5,-50 -5,-50 -15,-50 L -30,-50 C -40,-50 -45,-40 -45,-30 Z" fill="#94a3b8" stroke="#334155" strokeWidth="2" />

                  <path d="M -12,-47 L 6,-47 L 17,-35 L -12,-35 Z" fill="#e2e8f0" stroke="#94a3b8" strokeWidth="2" />
                  <line x1="0" y1="-47" x2="0" y2="-35" stroke="#94a3b8" strokeWidth="2" />

                  <path d="M 36,-30 L 43,-30 L 43,-25 L 36,-25 Z" fill="#e2e8f0" />
                  {/*<path d="M -45,-30 L -42,-30 L -42,-25 L -45,-25 Z" fill="#e2e8f0" />*/}
                </g>

                <g transform="translate(-25, -13)">
                  <circle cx="0" cy="0" r="12" fill="#1e293b" />
                  <circle cx="0" cy="0" r="6" fill="#cbd5e1" />
                  <g>
                    <animateTransform attributeName="transform" type="rotate" values="0; 360" dur="0.5s" repeatCount="indefinite" />
                    <line x1="0" y1="-6" x2="0" y2="6" stroke="#475569" strokeWidth="2" />
                    <line x1="-6" y1="0" x2="6" y2="0" stroke="#475569" strokeWidth="2" />
                  </g>
                </g>
                <g transform="translate(25, -13)">
                  <circle cx="0" cy="0" r="12" fill="#1e293b" />
                  <circle cx="0" cy="0" r="6" fill="#cbd5e1" />
                  <g>
                    <animateTransform attributeName="transform" type="rotate" values="0; 360" dur="0.5s" repeatCount="indefinite" />
                    <line x1="0" y1="-6" x2="0" y2="6" stroke="#475569" strokeWidth="2" />
                    <line x1="-6" y1="0" x2="6" y2="0" stroke="#475569" strokeWidth="2" />
                  </g>
                </g>
              </g>
            </g>

            <text x={VIEW_BOX_WIDTH / 2} y={VIEW_BOX_HEIGHT - 70} textAnchor="middle" fill="#475569" fontSize="20" fontWeight="600">
              Clusterization in progress...
            </text>
          </svg>
        </div>
      );
    }

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
            ))
            }
            <text x={VIEW_BOX_WIDTH / 2} y={VIEW_BOX_HEIGHT / 2} textAnchor="middle" fill="#475569" fontSize="26" fontWeight="bold">
              Idle Fleet Mileage: {virtualDistance} km
            </text>
            <text x={VIEW_BOX_WIDTH / 2} y={VIEW_BOX_HEIGHT / 1.88} textAnchor="middle" fill="#939eab" fontSize="10">
              Here you can beat the world record
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
            const isDimmedByCluster = hoveredClusterIdx !== null && p.clusterIdx !== hoveredClusterIdx;
            const isHighlightedByWarehouse = warehouseHighlightedOrderIds !== null && warehouseHighlightedOrderIds.has(p.id);
            const isDimmedByWarehouse = warehouseHighlightedOrderIds !== null && !warehouseHighlightedOrderIds.has(p.id);
            const isDimmed = isDimmedByCluster || isDimmedByWarehouse;
            const isHighlighted = isActiveCluster || isHighlightedByWarehouse;
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
                  opacity={isDimmed ? 0.2 : 1}
                  stroke={isHighlighted ? "#1e293b" : "none"}
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

          {/* Warehouse markers — rendered on top of order points */}
          {warehousePoints.map((wp) => {
            const WAREHOUSE_R = 13 / transform.scale;
            const isHovered = hoveredWarehouse?.id === wp.id;
            const isHighlighted = highlightedWarehouseId === wp.id;
            const isActive = isHovered || isHighlighted;
            return (
              <g
                key={`wh-${wp.id}`}
                onMouseEnter={(e) => showWarehouseTooltip(wp, e)}
                onMouseMove={(e) => {
                  if (containerRef.current) {
                    const rect = containerRef.current.getBoundingClientRect();
                    let left = e.clientX - rect.left + 15;
                    let top = e.clientY - rect.top + 15;
                    if (left + 180 > rect.width) left = e.clientX - rect.left - 180;
                    if (top + 80 > rect.height) top = e.clientY - rect.top - 80;
                    setWarehouseTooltipStyle(prev => ({ ...prev, left: `${left}px`, top: `${top}px` }));
                  }
                }}
                onMouseLeave={hideWarehouseTooltip}
                style={{ cursor: "pointer" }}
              >
                {/* Glow ring when active */}
                {isActive && (
                  <circle
                    cx={wp.x} cy={wp.y}
                    r={(WAREHOUSE_R + 3) / transform.scale * transform.scale}
                    fill="none"
                    stroke="#FACC15"
                    strokeWidth={3 / transform.scale}
                    // opacity={0.6}
                  />
                )}
                {/* Warehouse diamond shape */}
                <rect
                  x={wp.x - WAREHOUSE_R * 0.75}
                  y={wp.y - WAREHOUSE_R * 0.75}
                  width={WAREHOUSE_R * 1.5}
                  height={WAREHOUSE_R * 1.5}
                  rx={2 / transform.scale}
                  transform={`rotate(45, ${wp.x}, ${wp.y})`}
                  fill={isActive ? "#1e293b" : "#FACC15"}
                  stroke={isActive ? "#FACC15" : "#1e293b"}
                  strokeWidth={2 / transform.scale}
                />
                {/* Warehouse icon — "W" label */}
                <text
                  x={wp.x} y={wp.y + (3.5 / transform.scale)} // f8fafc 1e293b
                  textAnchor="middle" fill={isActive ? "#f8fafc" : "#1e293b"}
                  fontSize={8 / transform.scale} fontWeight="bold"
                  style={{ pointerEvents: "none", userSelect: "none" }}
                >
                  W{wp.id}
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

      {hoveredWarehouse && (
        <div
          className="bg-white border border-gray-200 rounded-lg shadow-xl p-3 text-sm w-[170px]"
          style={warehouseTooltipStyle}
        >
          <div className="flex items-center gap-2 font-semibold text-gray-800 border-b border-gray-200 pb-1 mb-2">
            <span className="inline-flex items-center justify-center w-5 h-5 rounded bg-yellow-400 text-gray-900 text-[10px] font-bold">W</span>
            Warehouse #{hoveredWarehouse.id}
          </div>
          <div className="text-gray-500 text-xs">
            {(() => {
              const taskOrders = getOrdersForTask(taskId);
              const count = taskOrders.filter(o => o.warehouseId === hoveredWarehouse.id).length;
              return <span>{count} order{count !== 1 ? 's' : ''} assigned</span>;
            })()}
          </div>
        </div>
      )}
    </div>
  );
}