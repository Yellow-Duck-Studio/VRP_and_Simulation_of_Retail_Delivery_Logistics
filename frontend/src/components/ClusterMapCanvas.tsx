import { useState, useMemo, useCallback, useRef, useId, useEffect } from "react";
import { mockOrders, type OrderInfo } from "../mockData";

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
  "#8b5cf6", "#f97316", "#06b6d4", "#84cc16", "#ec4899", "#6366f1",
  "#14b8a6", "#f59e0b", "#10b981", "#ef4444", "#0ea5e9", "#a855f7",
  "#e11d48", "#22c55e", "#eab308", "#3b82f6", "#8b5cf6", "#f43f5e",
];

const VIEW_BOX_WIDTH = 700;
const VIEW_BOX_HEIGHT = 600;
const POINT_RADIUS = 12;
const ARROW_OFFSET = POINT_RADIUS + 4;

function pointPosition(id: number) {
  const x = ((id * 137) % (VIEW_BOX_WIDTH - 40)) + 20;
  const y = ((id * 223) % (VIEW_BOX_HEIGHT - 40)) + 20;
  return { x, y };
}

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

export default function ClusterMap({ clusters }: ClusterMapProps) {
  const [virtualDistance, setVirtualDistance] = useState(0);
  const [hoveredPoint, setHoveredPoint] = useState<Point | null>(null);
  const [tooltipOrder, setTooltipOrder] = useState<OrderInfo | null>(null);
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({});
  const containerRef = useRef<HTMLDivElement>(null);
  const arrowId = useId();

  useEffect(() => {
    const interval = setInterval(() => {
      setVirtualDistance(prev => prev + Math.floor(Math.random() * 5) + 2);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const points: Point[] = useMemo(() => {
    const result: Point[] = [];
    clusters.forEach((cluster, ci) => {
      cluster.forEach((id, orderIdx) => {
        const { x, y } = pointPosition(id);
        result.push({ id, x, y, clusterIdx: ci, orderIdxInCluster: orderIdx });
      });
    });
    return result;
  }, [clusters]);

  const pointMap = useMemo(() => {
    const map = new Map<number, Point>();
    points.forEach((p) => map.set(p.id, p));
    return map;
  }, [points]);

  const hoveredClusterIdx = hoveredPoint ? hoveredPoint.clusterIdx : null;

  const showTooltip = useCallback(
    (point: Point, event: React.MouseEvent) => {
      setHoveredPoint(point);
      setTooltipOrder(mockOrders[point.id] ?? null);

      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        let left = event.clientX - rect.left + 15;
        let top = event.clientY - rect.top + 15;

        if (left + 200 > rect.width) left = event.clientX - rect.left - 200;
        if (top + 120 > rect.height) top = event.clientY - rect.top - 120;

        setTooltipStyle({
          left: `${left}px`,
          top: `${top}px`,
          position: "absolute",
          zIndex: 10,
          pointerEvents: "none",
        });
      }
    },
    []
  );

  const hideTooltip = useCallback(() => {
    setHoveredPoint(null);
    setTooltipOrder(null);
  }, []);

  if (!clusters || clusters.length === 0) {
    const idlePath = "M 150,300 L 250,150 L 450,150 L 550,300 L 450,450 L 250,450 Z";

    const idleCars = [
      { fill: "#3b82f6", begin: "0s" },
      { fill: "#f59e0b", begin: "-4s" },
      { fill: "#ea74e8", begin: "-8s" },
    ];

    return (
      <div className="relative w-full overflow-hidden border border-gray-200 rounded-lg bg-slate-50 flex items-center justify-center">
        <svg
          viewBox={`0 0 ${VIEW_BOX_WIDTH} ${VIEW_BOX_HEIGHT}`}
          className="w-full h-auto"
          preserveAspectRatio="xMidYMid meet"
          style={{ maxHeight: "600px" }}
        >

          <path
            d={idlePath}
            fill="none"
            stroke="#cbd5e1"
            strokeWidth="2"
          />

          <circle cx="150" cy="300" r="9" fill="#94a3b8" />
          <text x="150" y="300" textAnchor="middle" dominantBaseline="middle" fill="#f8fafc" fontSize="12" fontWeight="bold">
            5
          </text>

          <circle cx="250" cy="150" r="9" fill="#94a3b8" />
          <text x="250" y="150" textAnchor="middle" dominantBaseline="middle" fill="#f8fafc" fontSize="12" fontWeight="bold">
            9
          </text>
          <circle cx="450" cy="150" r="9" fill="#94a3b8" />
          <text x="450" y="150" textAnchor="middle" dominantBaseline="middle" fill="#f8fafc" fontSize="12" fontWeight="bold">
            3
          </text>
          <circle cx="550" cy="300" r="9" fill="#94a3b8" />
          <text x="550" y="300" textAnchor="middle" dominantBaseline="middle" fill="#f8fafc" fontSize="12" fontWeight="bold">
            2
          </text>
          <circle cx="450" cy="450" r="9" fill="#94a3b8" />
          <text x="450" y="450" textAnchor="middle" dominantBaseline="middle" fill="#f8fafc" fontSize="12" fontWeight="bold">
            7
          </text>
          <circle cx="250" cy="450" r="9" fill="#94a3b8" />
          <text x="250" y="450" textAnchor="middle" dominantBaseline="middle" fill="#f8fafc" fontSize="12" fontWeight="bold">
            1
          </text>

          {idleCars.map((car, index) => (
            <g key={index}>
              {/* Body */}
              <rect x="-12" y="-7" width="24" height="14" rx="3" fill={car.fill} stroke="#ffffff" strokeWidth="1.5" />
              {/* Windshield */}
              <rect x="1" y="-5" width="5" height="10" rx="1" fill="#1e293b" opacity="0.5" />
              {/* Rear window */}
              <rect x="-8" y="-5" width="3" height="10" rx="1" fill="#1e293b" opacity="0.5" />
              {/* Lights */}
              <rect x="10" y="-5" width="2" height="3" fill="#fef08a" />
              <rect x="10" y="2" width="2" height="3" fill="#fef08a" />

              <animateMotion
                dur="12s"
                begin={car.begin}
                repeatCount="indefinite"
                path={idlePath}
                rotate="auto"
              />
            </g>
          ))}

          <text x={VIEW_BOX_WIDTH / 2} y={VIEW_BOX_HEIGHT / 2} textAnchor="middle" fill="#475569" fontSize="28" fontWeight="bold">
            Idle Fleet Mileage: {virtualDistance} km
          </text>
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
        viewBox={`0 0 ${VIEW_BOX_WIDTH} ${VIEW_BOX_HEIGHT}`}
        className="w-full h-auto"
        preserveAspectRatio="xMidYMid meet"
        style={{ maxHeight: "600px" }}
      >
        <defs>
          <marker
            id={arrowId}
            viewBox="0 0 12 12"
            refX="10"
            refY="6"
            markerWidth="8"
            markerHeight="8"
            orient="auto"
          >
            <path d="M 0 0 L 12 6 L 0 12 z" fill="#6b7280" />
          </marker>
        </defs>

        {hoveredClusterIdx !== null &&
          clusters[hoveredClusterIdx].map((id, i, arr) => {
            if (i === arr.length - 1) return null;
            const from = pointMap.get(id);
            const to = pointMap.get(arr[i + 1]);
            if (!from || !to) return null;

            const { x1, y1, x2, y2 } = shortenLine(
              from.x, from.y,
              to.x, to.y,
              ARROW_OFFSET,
              ARROW_OFFSET
            );

            return (
              <line
                key={`arrow-${id}-${arr[i + 1]}`}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke="#6b7280"
                strokeWidth={1}
                markerEnd={`url(#${arrowId})`}
              />
            );
          })}

        {points.map((p) => {
          const isActiveCluster = hoveredClusterIdx !== null && p.clusterIdx === hoveredClusterIdx;
          const isDimmed = hoveredClusterIdx !== null && p.clusterIdx !== hoveredClusterIdx;
          const opacity = isDimmed ? 0.25 : 1;
          const stroke = isActiveCluster ? "#374151" : "none";
          const strokeWidth = isActiveCluster ? 2 : 0;

          return (
            <g
              key={p.id}
              onMouseEnter={(e) => showTooltip(p, e)}
              onMouseMove={(e) => {
                if (containerRef.current) {
                  const rect = containerRef.current.getBoundingClientRect();
                  let left = e.clientX - rect.left + 15;
                  let top = e.clientY - rect.top + 15;
                  if (left + 200 > rect.width) left = e.clientX - rect.left - 200;
                  if (top + 120 > rect.height) top = e.clientY - rect.top - 120;
                  setTooltipStyle((prev) => ({
                    ...prev,
                    left: `${left}px`,
                    top: `${top}px`,
                  }));
                }
              }}
              onMouseLeave={hideTooltip}
              style={{ cursor: "pointer" }}
            >
              <circle
                cx={p.x}
                cy={p.y}
                r={POINT_RADIUS}
                fill={COLORS[p.clusterIdx % COLORS.length]}
                opacity={opacity}
                stroke={stroke}
                strokeWidth={strokeWidth}
              />
              <text
                x={p.x}
                y={p.y + 4}
                textAnchor="middle"
                fill="white"
                fontSize="9"
                fontWeight="bold"
                style={{ pointerEvents: "none", userSelect: "none" }}
              >
                {p.id}
              </text>
            </g>
          );
        })}
      </svg>

      {tooltipOrder && (
        <div
          className="bg-white border border-gray-300 rounded-lg shadow-md p-2 text-sm w-48"
          style={tooltipStyle}
        >
          <div className="font-semibold">Order #{tooltipOrder.id}</div>
          <div>Address: {tooltipOrder.address}</div>
          <div>Weight: {tooltipOrder.weight} kg</div>
          <div>Volume: {tooltipOrder.volume} m³</div>
          <div>Time window: {tooltipOrder.timeWindow}</div>
        </div>
      )}
    </div>
  );
}