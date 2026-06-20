import { useState, useMemo, useCallback, useRef, useId } from "react";
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
  const [hoveredPoint, setHoveredPoint] = useState<Point | null>(null);
  const [tooltipOrder, setTooltipOrder] = useState<OrderInfo | null>(null);
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({});
  const containerRef = useRef<HTMLDivElement>(null);
  const arrowId = useId();

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