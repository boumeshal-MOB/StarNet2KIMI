import { useMemo, useState } from "react";
import type { AdjustedPoint } from "@/lib/types";

interface Props {
  points: AdjustedPoint[];
  sights?: { station_id: string; target_id: string }[];
  showEllipses?: boolean;
  height?: number;
}

/** Plan view: stations as squares, references as diamonds, monitoring as dots,
 * 95% confidence ellipses (exaggerated for legibility), observation links. */
export function NetworkMap({ points, sights = [], showEllipses = true, height = 380 }: Props) {
  const [hover, setHover] = useState<string | null>(null);
  const ELLIPSE_SCALE = 40; // ellipses are mm-scale — exaggerate to stay visible

  const view = useMemo(() => {
    if (points.length === 0) return null;
    const es = points.map((p) => p.e);
    const ns = points.map((p) => p.n);
    const pad = 12;
    const minE = Math.min(...es) - pad;
    const maxE = Math.max(...es) + pad;
    const minN = Math.min(...ns) - pad;
    const maxN = Math.max(...ns) + pad;
    const width = 760;
    const scale = Math.min(width / (maxE - minE), height / (maxN - minN));
    const x = (e: number) => (e - minE) * scale + (width - (maxE - minE) * scale) / 2;
    const y = (n: number) => height - (n - minN) * scale - (height - (maxN - minN) * scale) / 2;
    return { x, y, scale, width };
  }, [points, height]);

  if (!view) {
    return <div className="flex h-40 items-center justify-center text-sm text-slate-400">—</div>;
  }

  const byId = new Map(points.map((p) => [p.id, p]));
  const hovered = hover ? byId.get(hover) : null;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${view.width} ${height}`} className="w-full rounded-lg bg-slate-50 ring-1 ring-slate-200">
        {sights.map((sight, index) => {
          const a = byId.get(sight.station_id);
          const b = byId.get(sight.target_id);
          if (!a || !b) return null;
          const active = hover === sight.station_id || hover === sight.target_id;
          return (
            <line
              key={index}
              x1={view.x(a.e)}
              y1={view.y(a.n)}
              x2={view.x(b.e)}
              y2={view.y(b.n)}
              stroke={active ? "#2563eb" : "#cbd5e1"}
              strokeWidth={active ? 1.4 : 0.7}
            />
          );
        })}
        {showEllipses &&
          points
            .filter((p) => p.role !== "station" && p.ellipse_semi_major_m > 0)
            .map((p) => (
              <ellipse
                key={`ell-${p.id}`}
                cx={view.x(p.e)}
                cy={view.y(p.n)}
                rx={Math.max(p.ellipse_semi_major_m * ELLIPSE_SCALE * view.scale, 2.5)}
                ry={Math.max(p.ellipse_semi_minor_m * ELLIPSE_SCALE * view.scale, 2.5)}
                transform={`rotate(${p.ellipse_orientation_deg} ${view.x(p.e)} ${view.y(p.n)})`}
                fill="#3b82f620"
                stroke="#3b82f6"
                strokeWidth={0.8}
              />
            ))}
        {points.map((p) => {
          const cx = view.x(p.e);
          const cy = view.y(p.n);
          const common = { onMouseEnter: () => setHover(p.id), onMouseLeave: () => setHover(null), className: "cursor-pointer" };
          if (p.role === "station") {
            return (
              <g key={p.id} {...common}>
                <rect x={cx - 5} y={cy - 5} width={10} height={10} fill="#0f172a" stroke="#fff" strokeWidth={1.5} transform={`rotate(45 ${cx} ${cy})`} />
                <text x={cx + 9} y={cy - 6} fontSize={11} fontWeight={600} fill="#0f172a">
                  {p.id}
                </text>
              </g>
            );
          }
          if (p.role === "reference") {
            return (
              <g key={p.id} {...common}>
                <rect x={cx - 4.5} y={cy - 4.5} width={9} height={9} fill="#059669" stroke="#fff" strokeWidth={1.4} transform={`rotate(45 ${cx} ${cy})`} />
                <text x={cx + 8} y={cy + 3} fontSize={10} fontWeight={600} fill="#047857">
                  {p.id}
                </text>
              </g>
            );
          }
          const hoveredPt = hover === p.id;
          return (
            <g key={p.id} {...common}>
              <circle cx={cx} cy={cy} r={hoveredPt ? 5.5 : 3.5} fill="#2563eb" stroke="#fff" strokeWidth={1.2} />
              {hoveredPt && (
                <text x={cx + 8} y={cy + 3} fontSize={10} fontWeight={600} fill="#1d4ed8">
                  {p.id.replace("PP_", "")}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {hovered && (
        <div className="pointer-events-none absolute right-3 top-3 rounded-lg bg-slate-900/95 px-3 py-2 text-[11px] leading-relaxed text-white shadow-lg">
          <div className="font-semibold">{hovered.id}</div>
          <div className="font-mono text-slate-300">
            E {hovered.e.toFixed(4)} · N {hovered.n.toFixed(4)} · H {hovered.h.toFixed(4)}
          </div>
          {hovered.delta_e !== undefined && hovered.delta_n !== undefined && hovered.delta_h !== undefined && (
            <div className="font-mono text-sky-300">
              Δ {(hovered.delta_e * 1000).toFixed(1)} / {(hovered.delta_n * 1000).toFixed(1)} / {(hovered.delta_h * 1000).toFixed(1)} mm
            </div>
          )}
          <div className="text-slate-400">
            σ {(hovered.sigma_e * 1000).toFixed(1)} / {(hovered.sigma_n * 1000).toFixed(1)} / {(hovered.sigma_h * 1000).toFixed(1)} mm
          </div>
        </div>
      )}
      <div className="mt-2 flex items-center gap-4 text-[11px] text-slate-500">
        <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rotate-45 bg-slate-900" /> Station</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rotate-45 bg-emerald-600" /> Reference</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-full bg-blue-600" /> Monitoring</span>
        {showEllipses && <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-full border border-blue-500 bg-blue-500/15" /> Ellipse 95% (×{ELLIPSE_SCALE})</span>}
      </div>
    </div>
  );
}
