import React, { useState, useRef, ElementType, useEffect, useCallback } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line,
} from "recharts";
import {
  Settings, HelpCircle, User, Download, Plus, TrendingUp, TrendingDown,
  CheckCircle2, XCircle, AlertCircle, Upload, RefreshCw, Filter, FileDown,
  Play, ArrowRight, BarChart3, Layers, ShoppingCart, Map, Sliders,
  Package2, GitCompare, LayoutDashboard, Link, Clock, Gauge, History,
  Save, ClipboardList, Trash2,
} from "lucide-react";
import * as XLSX from "xlsx";

// ── Palette ─────────────────────────────────────────────────────────────────
const C = {
  navy:    "#1E3A5F",
  blue:    "#2E86AB",
  green:   "#27AE60",
  orange:  "#F39C12",
  red:     "#E74C3C",
  gray:    "#F8F9FA",
  border:  "#E9ECEF",
  muted:   "#6C757D",
} as const;

const FC: Record<string, string> = {
  CRC:  "#2E86AB",
  HDG:  "#1E3A5F",
  PPGI: "#F39C12",
  BACR: "#ADB5BD",
};

// ── Types ──────────────────────────────────────────────────────────────────

type ImportSession = {
  id: string;
  fileName: string;
  importedAt: string;
  overridesData?: OverrideParams;
};

type StockOverride = { init?: number; min?: number; max?: number };

type OverrideParams = {
  prix_zinc: string;
  conso_zinc_hdg: string;
  conso_zinc_ppgi: string;
  prix_peinture: string;
  conso_peinture: string;
  pen_haute: string;
  pen_normale: string;
  pen_basse: string;
  cout_stock_inter: string;
  cout_stock_fini: string;
  prix_chute: string;
  coef_decl: string;
  coef_nc: string;
  stock_pk: Record<string, StockOverride>;
  stock_inter: Record<string, StockOverride>;
  stock_fini: Record<string, StockOverride>;
  dispo_hrc: Record<string, string>;
  arrets: Record<string, string>;
};

const DEFAULT_OVERRIDES: OverrideParams = {
  prix_zinc: "", conso_zinc_hdg: "", conso_zinc_ppgi: "",
  prix_peinture: "", conso_peinture: "",
  pen_haute: "", pen_normale: "", pen_basse: "",
  cout_stock_inter: "", cout_stock_fini: "",
  prix_chute: "", coef_decl: "", coef_nc: "",
  stock_pk: { DC01: {}, DD13: {}, DX51: {}, DX52: {}, S320: {} },
  stock_inter: { 'FH-CRMA': {}, 'FH-CRMB': {}, 'BAF-out': {}, 'SKP-out': {} },
  stock_fini: { CRC: {}, HDG: {}, PPGI: {}, BACR: {} },
  dispo_hrc: { DC01: "", DD13: "", DX51: "", DX52: "", S320: "" },
  arrets: {},
};

type SimParams = {
  gap: number;
  campagneActive: boolean;
  activerB2: boolean;
  overrides: OverrideParams;
};

type RunResult = {
  id: number;
  importId: string;
  runType: 'base' | 'personnalise';
  label: string;
  executedAt: string;
  duree: string;
  saved: boolean;
  paramsUsed: {
    gap: number;
    campagneActive: boolean;
    overrides: OverrideParams;
  };
  marge: number;
  tauxService: number;
  commandes: string;
  weekly: Array<{ sem: string; CRC: number; HDG: number; PPGI: number; BACR: number }>;
  margeFamily: Array<{ name: string; value: number; pct: number }>;
  statutData: Array<{ name: string; value: number; pct: number; color: string }>;
  lignes: Array<{
    ligne: string;
    cap: number;
    s: Array<{ t: number; p: number; capacite: number }>;
    moy: number;
  }>;
  contraintes: Array<{ contrainte: string; cm: number; client: string; produit: string }>;
  refusees: Array<{
    id: string;
    client: string;
    produit: string;
    tonnage: number;
    raison: string;
    contraintes_bloquantes: string[];
  }>;
  stockChartData: Array<{ t: string; [key: string]: number | string }>;
  commandesDetail: any[];
  exportFile: string | null;
  commandesRefuseesCount: number;
  commandesRefuseesTonnage: number;
  utilisationMoyenne: number;
  planProduction: Array<{
    commande: string;
    famille: string;
    grade: string;
    chemin: number;
    machine: string;
    semaine: number;
    tonnage_entrant: number;
    rendement: number;
    tonnage_sortant: number;
  }>;
  stockPkTotal: Array<{ t: string; PK: number }>;
  stockPkByGrade: Array<{ t: string; DC01?: number; DD13?: number; DX51?: number; DX52?: number; S320?: number }>;
  stockFiniByFamille: Array<{ t: string; CRC?: number; HDG?: number; PPGI?: number; BACR?: number }>;
  stockInterByPoint: Array<{ t: string; 'FH-CRMA'?: number; 'FH-CRMB'?: number; 'BAF-out'?: number; 'SKP-out'?: number }>;
  consoHrcByGrade: Array<{ t: string; DC01?: number; DD13?: number; DX51?: number; DX52?: number; S320?: number }>;
  bnbTree: {
    nodes: Array<{
      nodeId: number;
      nodesLeft: number;
      bestBound: number;
      bestInt: number;
      gap: number;
    }>;
    totalLeaves: number;
    bestBoundEvolution: number[];
  } | null;
};

type Commande = {
  id: string; client: string; famille: string; grade: string;
  ep: number; larg: number; ton: number; prio: string;
  semLiv: number; statut: string; semProd: number | null; retard: number;
  margeMad: number;
  margeUnitaireMad: number;
  prixVente: number;
};

// ── Composants partagés ────────────────────────────────────────────────────

function ProgressBar({ pct }: { pct: number }) {
  const color = pct >= 100 ? C.red : pct >= 90 ? C.orange : C.blue;
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex-1 bg-gray-200 rounded-full h-1.5">
        <div className="h-1.5 rounded-full" style={{ width: `${Math.min(pct, 100)}%`, backgroundColor: color }} />
      </div>
      <span className="text-xs font-mono w-11 text-right tabular-nums" style={{ color }}>
        {pct.toFixed(1)}%
      </span>
    </div>
  );
}

function Badge({ label, bg, text }: { label: string; bg: string; text: string }) {
  return (
    <span className="text-xs font-medium px-2 py-0.5 rounded-full" style={{ backgroundColor: bg, color: text }}>
      {label}
    </span>
  );
}

function StatutBadge({ statut }: { statut: string }) {
  const map: Record<string, [string, string]> = {
    "Honorée":   ["#ECFDF5", C.green],
    "En avance": ["#EFF6FF", C.blue],
    "En retard": ["#FFF7ED", C.orange],
    "Refusée":   ["#FEF2F2", C.red],
  };
  const [bg, text] = map[statut] ?? ["#F3F4F6", C.muted];
  return <Badge label={statut} bg={bg} text={text} />;
}

function FamilleBadge({ fam }: { fam: string }) {
  return <Badge label={fam} bg={C.navy + "18"} text={C.navy} />;
}

function Card({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded border border-gray-200 flex flex-col">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100">
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: C.muted }}>{title}</span>
        {action}
      </div>
      <div className="flex-1">{children}</div>
    </div>
  );
}

function KPICard({ label, value, sub, trend, up, Icon, color }: {
  label: string; value: string; sub?: string; trend?: string; up?: boolean;
  Icon: ElementType; color: string;
}) {
  return (
    <div className="bg-white rounded border border-gray-200 p-3.5 flex gap-3 min-w-0">
      <div className="w-9 h-9 rounded flex items-center justify-center flex-shrink-0" style={{ backgroundColor: color + "1A" }}>
        <Icon size={16} style={{ color }} />
      </div>
      <div className="min-w-0">
        <p className="text-xs uppercase tracking-wide truncate" style={{ color: C.muted }}>{label}</p>
        <p className="text-lg font-bold leading-tight tabular-nums" style={{ color: C.navy, fontFamily: "'DM Mono', monospace" }}>{value}</p>
        {sub && <p className="text-xs mt-0.5 truncate" style={{ color: C.muted }}>{sub}</p>}
        {trend && (
          <p className="text-xs mt-0.5 flex items-center gap-0.5" style={{ color: up ? C.green : C.red }}>
            {up ? <TrendingUp size={9} /> : <TrendingDown size={9} />}
            {trend}
          </p>
        )}
      </div>
    </div>
  );
}

function ThTable({ headers, children }: { headers: string[]; children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-100">
            {headers.map(h => (
              <th key={h} className="text-left px-3 py-2 font-semibold uppercase tracking-wide whitespace-nowrap" style={{ color: C.muted }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function Tr({ i, children }: { i: number; children: React.ReactNode }) {
  return (
    <tr className={`border-b border-gray-50 hover:bg-blue-50/20 transition-colors ${i % 2 !== 0 ? "bg-gray-50/40" : ""}`}>
      {children}
    </tr>
  );
}

// ── Composant MultiLine pour les stocks ──────────────────────────────────

function MultiLineStockCard({ title, data, seriesKeys, colors }: {
  title: string; data: any[]; seriesKeys: string[]; colors: Record<string, string>;
}) {
  const [visible, setVisible] = useState<Record<string, boolean>>(
    Object.fromEntries(seriesKeys.map(k => [k, true]))
  );
  return (
    <Card title={title}>
      <div className="p-4">
        <div className="flex gap-3 mb-3 flex-wrap">
          {seriesKeys.map(k => (
            <label key={k} className="flex items-center gap-1.5 text-xs cursor-pointer">
              <input type="checkbox" checked={visible[k]}
                onChange={() => setVisible(v => ({ ...v, [k]: !v[k] }))} />
              <span style={{ color: colors[k] ?? C.muted }}>{k}</span>
            </label>
          ))}
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 4, right: 16, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F0F0F0" />
            <XAxis dataKey="t" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip formatter={(v: number) => `${v.toLocaleString()} T`} />
            <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
            {seriesKeys.filter(k => visible[k]).map(k => (
              <Line key={k} type="monotone" dataKey={k} stroke={colors[k] ?? C.navy} strokeWidth={2} dot={{ r: 3 }} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

// ── Pages ────────────────────────────────────────────────────────────────────

// --- TÂCHE 1.3 - RefuseesCard ---
function RefuseesCard({ refusees }: { refusees: RunResult['refusees'] }) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const toggle = (id: string) => setExpanded(prev => ({ ...prev, [id]: !prev[id] }));

  return (
    <Card title="Commandes refusées (Extrait)" action={
      <button className="text-xs flex items-center gap-1 transition-colors hover:opacity-70" style={{ color: C.blue }}>
        Voir toutes <ArrowRight size={10} />
      </button>
    }>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-100">
              <th className="px-2 py-2 w-6" />
              {["ID","Client","Produit","Tonnage (T)","Raison","Détails"].map(h => (
                <th key={h} className="text-left px-3 py-2 font-semibold uppercase tracking-wide whitespace-nowrap" style={{ color: C.muted }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {refusees.slice(0, 5).map((c, i) => {
              const hasDetails = c.contraintes_bloquantes && c.contraintes_bloquantes.length > 0;
              const isOpen = expanded[c.id];
              return (
                <React.Fragment key={c.id}>
                  <tr className={`border-b border-gray-50 hover:bg-blue-50/20 transition-colors ${i % 2 !== 0 ? "bg-gray-50/40" : ""}`}>
                    <td className="px-2 py-2 text-center">
                      <button
                        onClick={() => hasDetails && toggle(c.id)}
                        style={{ color: hasDetails ? C.blue : C.border, cursor: hasDetails ? 'pointer' : 'default' }}
                        className="font-bold text-sm leading-none"
                      >
                        {isOpen ? '▼' : '▶'}
                      </button>
                    </td>
                    <td className="px-3 py-2 font-mono font-semibold" style={{ color: C.blue }}>{c.id}</td>
                    <td className="px-3 py-2" style={{ color: C.navy }}>{c.client}</td>
                    <td className="px-3 py-2 text-xs" style={{ color: C.muted }}>{c.produit}</td>
                    <td className="px-3 py-2 font-mono tabular-nums text-right">{c.tonnage}</td>
                    <td className="px-3 py-2">
                      <Badge label={c.raison} bg="#FEF2F2" text={C.red} />
                    </td>
                    <td className="px-3 py-2">
                      {hasDetails
                        ? <span className="text-xs" style={{ color: C.blue }}>{c.contraintes_bloquantes.length} contrainte(s)</span>
                        : <span className="text-xs" style={{ color: C.muted }}>—</span>
                      }
                    </td>
                  </tr>
                  {isOpen && (
                    <tr>
                      <td colSpan={7} style={{ backgroundColor: '#FEF9F9', borderBottom: `1px solid ${C.border}` }}>
                        <div className="px-6 py-3">
                          <p className="font-semibold mb-2 text-xs" style={{ color: C.red }}>Contraintes bloquantes :</p>
                          {hasDetails ? (
                            <ul className="space-y-1">
                              {c.contraintes_bloquantes.map((ct, idx) => (
                                <li key={idx} className="flex items-start gap-2 text-xs" style={{ color: C.navy }}>
                                  <span style={{ color: C.red }} className="mt-0.5 flex-shrink-0">•</span>
                                  {ct}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-xs" style={{ color: C.muted }}>Aucun détail disponible</p>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// --- DashboardPage ---
function DashboardPage({ data, onConfigure, onSave }: { data: RunResult; onConfigure: () => void; onSave: () => void }) {
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          onClick={onConfigure}
          className="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded border border-blue-200 text-blue-600 hover:bg-blue-50 transition-colors"
        >
          <Link size={12} /> Configurer un scénario
        </button>
        {!data.saved && (
          <button
            className="ml-2 text-xs flex items-center gap-1.5 px-3 py-1.5 rounded border border-green-200 text-green-600 hover:bg-green-50 transition-colors"
            onClick={onSave}
          >
            <Save size={12} /> Enregistrer ce résultat
          </button>
        )}
      </div>

      <div className="grid grid-cols-7 gap-3">
        <KPICard label="Marge totale" value={`${(data.marge ).toLocaleString('fr-FR')} MMAD`}  Icon={TrendingUp} color={C.blue} />
        <KPICard label="Taux de service" value={`${data.tauxService.toFixed(1)} %`}  Icon={CheckCircle2} color={C.green} />
        <KPICard label="Cmd. honorées" value={data.commandes}  Icon={ShoppingCart} color={C.blue} />
        <KPICard label="Cmd. refusées" value={data.commandesRefuseesCount.toString()} sub={`${data.commandesRefuseesTonnage.toFixed(0)} T non honorées`} up={false} Icon={XCircle} color={C.orange} />
        <KPICard label="Util. moyenne" value={`${data.utilisationMoyenne.toFixed(1)} %`} sub="Toutes lignes" Icon={BarChart3} color={C.navy} />
        <KPICard label="Temps exécution" value={data.duree} Icon={Clock} color={C.blue} />
        <KPICard label="Gap" value={`${data.paramsUsed.gap.toFixed(3)} %`} Icon={Gauge} color={C.orange} />
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Card title="Plan de marche global (T produit fini)">
          <div className="p-3">
            <ResponsiveContainer width="100%" height={210}>
              <BarChart data={data.weekly} margin={{ top:4, right:4, left:-22, bottom:0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F0F0F0" />
                <XAxis dataKey="sem" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip formatter={(v: number) => `${v.toLocaleString()} T`} />
                <Legend iconSize={9} wrapperStyle={{ fontSize: 10 }} />
                <Bar dataKey="CRC"  stackId="a" fill={FC.CRC}  />
                <Bar dataKey="HDG"  stackId="a" fill={FC.HDG}  />
                <Bar dataKey="PPGI" stackId="a" fill={FC.PPGI} />
                <Bar dataKey="BACR" stackId="a" fill={FC.BACR} radius={[2,2,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Répartition de la marge par famille">
          <div className="p-3 flex items-center gap-2">
            <div style={{ width: 130, height: 210, flexShrink: 0 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={data.margeFamily} dataKey="value" cx="50%" cy="50%" innerRadius={42} outerRadius={60} paddingAngle={2}>
                    {data.margeFamily.map((_, i) => <Cell key={i} fill={[C.navy, C.blue, C.orange, C.muted][i]} />)}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex-1 space-y-1 min-w-0">
              <div className="text-center mb-2">
                <div className="text-xl font-bold tabular-nums" style={{ color: C.navy, fontFamily: "'DM Mono', monospace" }}>
                  {(data.marge * 1_000_000).toLocaleString('fr-FR')}
                </div>
                <div className="text-xs" style={{ color: C.muted }}>MAD total</div>
              </div>
              {data.margeFamily.map((f, i) => (
                <div key={f.name} className="flex items-center gap-1.5 text-xs">
                  <div className="w-2 h-2 rounded-sm flex-shrink-0" style={{ backgroundColor: [C.navy, C.blue, C.orange, C.muted][i] }} />
                  <span className="font-medium" style={{ color: C.navy }}>{f.name}</span>
                  <span className="ml-auto tabular-nums" style={{ color: C.muted }}>
                    {(f.value ).toLocaleString('fr-FR')} MMAD
                  </span>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <Card title="Commandes par statut (Tonnage)">
          <div className="p-3 flex items-center gap-2">
            <div style={{ width: 120, height: 210, flexShrink: 0 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={data.statutData} dataKey="value" cx="50%" cy="50%" innerRadius={38} outerRadius={56} paddingAngle={2}>
                    {data.statutData.map((s, i) => <Cell key={i} fill={s.color} />)}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex-1 space-y-2 min-w-0">
              <div className="text-center mb-2">
                <div className="text-lg font-bold tabular-nums" style={{ color: C.navy, fontFamily: "'DM Mono', monospace" }}>
                  {data.statutData.reduce((acc, s) => acc + s.value, 0).toLocaleString()}
                </div>
                <div className="text-xs" style={{ color: C.muted }}>T total</div>
              </div>
              {data.statutData.map(s => (
                <div key={s.name} className="text-xs">
                  <div className="flex items-center gap-1.5">
                    <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: s.color }} />
                    <span className="leading-tight truncate" style={{ color: C.navy }}>{s.name}</span>
                  </div>
                  <div className="ml-3.5 tabular-nums" style={{ color: C.muted }}>{s.value.toLocaleString()} T ({s.pct}%)</div>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>

      <Card title="Utilisation des lignes par semaine">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                <th className="text-left px-3 py-2 font-semibold uppercase tracking-wide" style={{ color: C.muted }}>Ligne</th>
                <th className="text-right px-3 py-2 font-semibold uppercase tracking-wide" style={{ color: C.muted }}>Capacité (T)</th>
                {["Semaine 1","Semaine 2","Semaine 3","Semaine 4"].map(s => (
                  <th key={s} colSpan={2} className="text-center px-3 py-2 font-semibold uppercase tracking-wide" style={{ color: C.muted }}>{s}</th>
                ))}
                <th className="text-right px-3 py-2 font-semibold uppercase tracking-wide" style={{ color: C.muted }}>Moy.</th>
              </tr>
              <tr className="bg-gray-50/60 border-b border-gray-100 text-xs" style={{ color: C.muted }}>
                <th /><th />
                {[0,1,2,3].map(i => (
                  <React.Fragment key={i}>
                    <th className="text-right px-2 py-1 font-normal">Tonnage</th>
                    <th className="px-2 py-1 font-normal min-w-[110px]">Util %</th>
                  </React.Fragment>
                ))}
                <th />
              </tr>
            </thead>
            <tbody>
              {data.lignes.map((row, ri) => (
                <tr key={row.ligne} className={`border-b border-gray-50 ${ri % 2 !== 0 ? "bg-gray-50/40" : ""}`}>
                  <td className="px-3 py-2 font-bold" style={{ color: C.navy }}>{row.ligne}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums" style={{ color: C.muted }}>{row.cap.toLocaleString()}</td>
                  {row.s.map((cell, si) => (
                    <React.Fragment key={si}>
                      <td className="px-2 py-2 text-right font-mono tabular-nums" style={{ color: cell.p >= 100 ? C.red : cell.p >= 90 ? C.orange : "inherit" }}>
                        {cell.t.toLocaleString()}
                        <span className="block text-[10px]" style={{ color: C.muted }}>
                          / {cell.capacite.toLocaleString()} T cap.
                        </span>
                      </td>
                      <td className="px-2 py-2 min-w-[110px]">
                        <ProgressBar pct={cell.p} />
                      </td>
                    </React.Fragment>
                  ))}
                  <td className="px-3 py-2 text-right">
                    <span className="font-mono text-xs px-1.5 py-0.5 rounded tabular-nums" style={{
                      backgroundColor: row.moy >= 90 ? "#FEF2F2" : row.moy >= 80 ? "#FFF7ED" : "#ECFDF5",
                      color: row.moy >= 90 ? C.red : row.moy >= 80 ? C.orange : C.green,
                    }}>
                      {row.moy.toFixed(1)}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-3">
        <Card title="Contraintes bloquantes (Top 5)" action={
          <button className="text-xs flex items-center gap-1 transition-colors hover:opacity-70" style={{ color: C.blue }}>
            Voir toutes <ArrowRight size={10} />
          </button>
        }>
          <ThTable headers={["Contrainte","Shadow Price","Client","Produit"]}>
            {data.contraintes.slice(0,5).map((c, i) => (
              <Tr key={i} i={i}>
                <td className="px-3 py-2" style={{ color: C.navy }}>{c.contrainte}</td>
                <td className="px-3 py-2 text-right font-mono font-semibold tabular-nums" style={{ color: C.navy }}>
                  {c.cm.toLocaleString("fr-MA", { minimumFractionDigits: 2 })}
                </td>
                <td className="px-3 py-2" style={{ color: C.muted }}>{c.client}</td>
                <td className="px-3 py-2"><FamilleBadge fam={c.produit} /></td>
              </Tr>
            ))}
          </ThTable>
        </Card>

        <RefuseesCard refusees={data.refusees} />
      </div>
    </div>
  );
}

// --- CommandesPage ---
function CommandesPage({ data }: { data: RunResult }) {
  const [famille, setFamille] = useState("Tous");
  const [statut, setStatut] = useState("Tous");
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc' | null>(null);

  const commandesSource = data.commandesDetail ?? [];

  let filtered = commandesSource.filter((c: Commande) =>
    (famille === "Tous" || c.famille === famille) &&
    (statut === "Tous" || c.statut === statut)
  );

  if (sortOrder === 'asc') {
    filtered = [...filtered].sort((a, b) => a.margeUnitaireMad - b.margeUnitaireMad);
  } else if (sortOrder === 'desc') {
    filtered = [...filtered].sort((a, b) => b.margeUnitaireMad - a.margeUnitaireMad);
  }

  const toggleSort = () => {
    if (sortOrder === null) setSortOrder('asc');
    else if (sortOrder === 'asc') setSortOrder('desc');
    else setSortOrder(null);
  };

  return (
    <div className="space-y-3">
      <div className="bg-white border border-gray-200 rounded p-3 flex items-center gap-3 flex-wrap">
        <Filter size={13} style={{ color: C.muted }} />
        <span className="text-xs font-medium" style={{ color: C.muted }}>Filtres :</span>
        {[
          { label: "Famille", value: famille, opts: ["Tous","HDG","CRC","PPGI","BACR"], set: setFamille },
          { label: "Statut",  value: statut,  opts: ["Tous","Honorée","En avance","En retard","Refusée"], set: setStatut },
        ].map(f => (
          <div key={f.label} className="flex items-center gap-1.5">
            <span className="text-xs" style={{ color: C.muted }}>{f.label} :</span>
            <select className="text-xs border border-gray-200 rounded px-2 py-1 bg-white focus:outline-none" value={f.value} onChange={e => f.set(e.target.value)}>
              {f.opts.map(o => <option key={o}>{o}</option>)}
            </select>
          </div>
        ))}
        <span className="ml-auto text-xs" style={{ color: C.muted }}>{filtered.length} commandes</span>

      </div>

      <Card title={`Commandes (${filtered.length})`}>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                {["ID","Client","Famille","Grade","Ép.","Larg.","Ton. (T)","Prix (MAD/T)","Marge/T (MAD/T)","Prio.","Sem. Liv.","Statut","Sem. Prod.","Retard","Actions"].map((h, idx) => {
                  if (h === "Marge/T (MAD/T)") {
                    return (
                      <th key={h} className="text-left px-3 py-2 font-semibold uppercase tracking-wide whitespace-nowrap cursor-pointer hover:text-blue-600" style={{ color: C.muted }} onClick={toggleSort}>
                        {h}
                        {sortOrder === 'asc' && <span className="ml-1">↑</span>}
                        {sortOrder === 'desc' && <span className="ml-1">↓</span>}
                        {sortOrder === null && <span className="ml-1">↕</span>}
                      </th>
                    );
                  }
                  return (
                    <th key={h} className="text-left px-3 py-2 font-semibold uppercase tracking-wide whitespace-nowrap" style={{ color: C.muted }}>
                      {h}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {filtered.map((c: Commande, i: number) => (
                <tr key={c.id} className={`border-b border-gray-50 hover:bg-blue-50/20 transition-colors ${i % 2 !== 0 ? "bg-gray-50/40" : ""}`}>
                  <td className="px-3 py-2 font-mono font-semibold" style={{ color: C.blue }}>{c.id}</td>
                  <td className="px-3 py-2" style={{ color: C.navy }}>{c.client}</td>
                  <td className="px-3 py-2"><FamilleBadge fam={c.famille} /></td>
                  <td className="px-3 py-2" style={{ color: C.muted }}>{c.grade}</td>
                  <td className="px-3 py-2 font-mono tabular-nums">{c.ep}</td>
                  <td className="px-3 py-2 font-mono tabular-nums">{c.larg}</td>
                  <td className="px-3 py-2 font-mono font-semibold tabular-nums" style={{ color: C.navy }}>{c.ton}</td>
                  <td className="px-3 py-2 font-mono tabular-nums" style={{ color: C.navy }}>
                    {(c.prixVente ?? 0).toLocaleString('fr-FR')}
                  </td>
                  <td className="px-3 py-2 font-mono tabular-nums" style={{ color: c.margeUnitaireMad > 0 ? C.green : C.red }}>
                    {c.margeUnitaireMad.toFixed(0)}
                  </td>
                  <td className="px-3 py-2">
                    <span className="font-mono text-xs px-1.5 py-0.5 rounded tabular-nums" style={{
                      backgroundColor: c.prio==="Haute"?"#FEF2F2":c.prio==="Normale"?"#FFF7ED":"#F3F4F6",
                      color: c.prio==="Haute"?C.red:c.prio==="Normale"?C.orange:C.muted,
                    }}>{c.prio}</span>
                  </td>
                  <td className="px-3 py-2 font-mono tabular-nums">S{c.semLiv}</td>
                  <td className="px-3 py-2"><StatutBadge statut={c.statut} /></td>
                  <td className="px-3 py-2 font-mono tabular-nums">{c.semProd != null ? `S${c.semProd}` : "—"}</td>
                  <td className="px-3 py-2">
                    {c.retard > 0
                      ? <Badge label={`+${c.retard} sem`} bg="#FFF7ED" text={C.orange} />
                      : <span style={{ color: C.border }}>—</span>
                    }
                  </td>
                  <td className="px-3 py-2">
                    <button className="text-xs px-2 py-0.5 rounded border border-gray-200 hover:border-blue-300 hover:text-blue-600 transition-colors">
                      Forcer
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

// --- PlanDeMarchePage ---
function PlanDeMarchePage({ data }: { data: RunResult }) {
  const machines = data.lignes.map(l => l.ligne);
  const [machine, setMachine] = useState(machines[0] || "PK");

  const ligne = data.lignes.find(l => l.ligne === machine);
  const ganttData = ligne ? ligne.s.map((cell, idx) => ({
    sem: `Sem. ${idx+1}`,
    Production: cell.t,
  })) : [];

  return (
    <div className="space-y-3">
      <div className="bg-white border border-gray-200 rounded p-3 flex items-center gap-3 flex-wrap">
        <span className="text-xs font-medium" style={{ color: C.muted }}>Machine :</span>
        <div className="flex flex-wrap gap-1">
          {machines.map(m => (
            <button key={m} onClick={() => setMachine(m)}
              className="text-xs px-3 py-1.5 rounded transition-all"
              style={{ backgroundColor: m===machine?C.navy:"#F3F4F6", color: m===machine?"white":C.navy, fontWeight: m===machine?600:400 }}>
              {m}
            </button>
          ))}
        </div>
      </div>

      <Card title={`Plan de marche – Machine ${machine}`}>
        <div className="p-4">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={ganttData} margin={{ top:4, right:16, left:-20, bottom:0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F0F0F0" />
              <XAxis dataKey="sem" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} label={{ value:"Tonnage (T)", angle:-90, position:"insideLeft", offset:12, style:{fontSize:10,fill:C.muted} }} />
              <Tooltip formatter={(v: number) => `${v.toLocaleString()} T`} />
              <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="Production" fill={C.blue} radius={[2,2,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card title="Tableau des flux détaillé (exemple)">
        <ThTable headers={["Commande","Client","Famille","Grade","Machine","Semaine","Tonnage (T)","Statut"]}>
          {(data.commandesDetail || []).slice(0,8).map((c: Commande, i: number) => (
            <Tr key={c.id} i={i}>
              <td className="px-3 py-2 font-mono font-semibold" style={{ color: C.blue }}>{c.id}</td>
              <td className="px-3 py-2" style={{ color: C.navy }}>{c.client}</td>
              <td className="px-3 py-2"><FamilleBadge fam={c.famille} /></td>
              <td className="px-3 py-2" style={{ color: C.muted }}>{c.grade}</td>
              <td className="px-3 py-2 font-semibold" style={{ color: C.navy }}>{machine}</td>
              <td className="px-3 py-2 font-mono tabular-nums">{c.semProd != null ? `Sem. ${c.semProd}` : "—"}</td>
              <td className="px-3 py-2 font-mono font-semibold tabular-nums" style={{ color: C.navy }}>{c.ton}</td>
              <td className="px-3 py-2"><StatutBadge statut={c.statut} /></td>
            </Tr>
          ))}
        </ThTable>
      </Card>
    </div>
  );
}

// --- PlanProductionPage ---
function PlanProductionPage({ data }: { data: RunResult | null }) {
  const [filterMachine, setFilterMachine] = useState('Toutes');
  const [filterSemaine, setFilterSemaine] = useState('Toutes');

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center h-64" style={{ color: C.muted }}>
        <AlertCircle size={32} className="mb-2" />
        <p className="text-lg font-semibold">Aucune simulation chargée</p>
        <p className="text-sm">Lancez une optimisation pour voir le plan de production détaillé.</p>
      </div>
    );
  }

  const rows = data.planProduction || [];
  const machines = ['Toutes', ...new Set(rows.map(r => r.machine))];
  const semaines = ['Toutes', ...new Set(rows.map(r => `S${r.semaine}`))];

  const filteredRows = rows.filter(r => {
    if (filterMachine !== 'Toutes' && r.machine !== filterMachine) return false;
    if (filterSemaine !== 'Toutes' && `S${r.semaine}` !== filterSemaine) return false;
    return true;
  });

  return (
    <div className="space-y-3">
      <div className="bg-white border border-gray-200 rounded p-3 flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium" style={{ color: C.muted }}>Machine :</span>
          <div className="flex flex-wrap gap-1">
            {machines.map(m => (
              <button key={m} onClick={() => setFilterMachine(m)}
                className="text-xs px-3 py-1.5 rounded transition-all"
                style={{
                  backgroundColor: m === filterMachine ? C.navy : "#F3F4F6",
                  color: m === filterMachine ? "white" : C.navy,
                  fontWeight: m === filterMachine ? 600 : 400,
                }}>
                {m}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium" style={{ color: C.muted }}>Semaine :</span>
          <div className="flex flex-wrap gap-1">
            {semaines.map(s => (
              <button key={s} onClick={() => setFilterSemaine(s)}
                className="text-xs px-3 py-1.5 rounded transition-all"
                style={{
                  backgroundColor: s === filterSemaine ? C.navy : "#F3F4F6",
                  color: s === filterSemaine ? "white" : C.navy,
                  fontWeight: s === filterSemaine ? 600 : 400,
                }}>
                {s}
              </button>
            ))}
          </div>
        </div>
        <span className="ml-auto text-xs" style={{ color: C.muted }}>{filteredRows.length} lignes</span>
      </div>

      <Card title={`Plan de production détaillé (${filteredRows.length} lignes)`}>
        <ThTable headers={["Commande","Famille","Grade","Machine","Semaine","Tonnage entrant (T)","Rendement (%)","Tonnage sortant (T)"]}>
          {filteredRows.map((r, i) => (
            <Tr key={i} i={i}>
              <td className="px-3 py-2 font-mono font-semibold" style={{ color: C.blue }}>{r.commande}</td>
              <td className="px-3 py-2"><FamilleBadge fam={r.famille} /></td>
              <td className="px-3 py-2" style={{ color: C.muted }}>{r.grade}</td>
              <td className="px-3 py-2 font-semibold" style={{ color: C.navy }}>{r.machine}</td>
              <td className="px-3 py-2 font-mono">S{r.semaine}</td>
              <td className="px-3 py-2 font-mono text-right">{r.tonnage_entrant.toFixed(1)}</td>
              <td className="px-3 py-2 font-mono text-right">{(r.rendement * 100).toFixed(1)}%</td>
              <td className="px-3 py-2 font-mono font-bold text-right" style={{ color: C.navy }}>{r.tonnage_sortant.toFixed(1)}</td>
            </Tr>
          ))}
        </ThTable>
      </Card>
    </div>
  );
}

// --- StocksPage ---
function StocksPage({ data }: { data: RunResult | null }) {
  if (!data) return <div className="text-center py-8" style={{ color: C.muted }}>Aucune donnée de stocks</div>;

  const gradeColors = { DC01: C.navy, DD13: C.blue, DX51: C.green, DX52: C.orange, S320: C.red };
  const interColors = { 'FH-CRMA': C.navy, 'FH-CRMB': C.blue, 'BAF-out': C.orange, 'SKP-out': C.green };

  return (
    <div className="grid grid-cols-2 gap-4">
      <MultiLineStockCard title="Consommation HRC par grade" data={data.consoHrcByGrade} seriesKeys={['DC01','DD13','DX51','DX52','S320']} colors={gradeColors} />
      <MultiLineStockCard title="Stock PK par grade" data={data.stockPkByGrade} seriesKeys={['DC01','DD13','DX51','DX52','S320']} colors={gradeColors} />
      <MultiLineStockCard title="Stock produits finis par famille" data={data.stockFiniByFamille} seriesKeys={['CRC','HDG','PPGI','BACR']} colors={FC} />
      <MultiLineStockCard title="Stock interprocess par point" data={data.stockInterByPoint} seriesKeys={['FH-CRMA','FH-CRMB','BAF-out','SKP-out']} colors={interColors} />
    </div>
  );
}

// --- ResultatsPage ---
function ResultatsPage({ data, onExport }: { data: RunResult; onExport: () => void }) {
  const [tab, setTab] = useState("Production");
  const [pageBNB, setPageBNB] = useState(0);
  const rowsPerPage = 50;

  const baseTabs = ["Production", "Commandes", "Marges", "Utilisation"];
  const bnbTab = (data.paramsUsed.campagneActive && data.bnbTree && data.bnbTree.nodes.length >= 2) ? ["B&B"] : [];
  const tabs = [...baseTabs, ...bnbTab];

  const bnbNodes = data.bnbTree?.nodes || [];
  const totalNodes = bnbNodes.length;
  const totalPages = Math.max(1, Math.ceil(totalNodes / rowsPerPage));
  const startIdx = pageBNB * rowsPerPage;
  const endIdx = Math.min(startIdx + rowsPerPage, totalNodes);
  const pageData = bnbNodes.slice(startIdx, endIdx);

  const handlePrev = () => setPageBNB(Math.max(0, pageBNB - 1));
  const handleNext = () => setPageBNB(Math.min(totalPages - 1, pageBNB + 1));

  return (
    <div className="space-y-3">
      <div className="bg-white border border-gray-200 rounded p-1 flex items-center gap-1">
        {tabs.map(t => (
          <button key={t} onClick={() => setTab(t)}
            className="text-xs px-4 py-2 rounded transition-all"
            style={{ backgroundColor: t===tab?C.navy:"transparent", color: t===tab?"white":C.muted, fontWeight: t===tab?600:400 }}>
            {t}
          </button>
        ))}
        <div className="ml-auto flex gap-2">
          <button
            onClick={onExport}
            className="text-xs px-3 py-1.5 border border-gray-200 rounded flex items-center gap-1.5 hover:bg-blue-50 hover:border-blue-200 transition-colors"
          >
            <FileDown size={10} /> Excel
          </button>
        </div>
      </div>

      {tab === "Production" && (
        <div className="space-y-3">
          <div className="bg-white p-3 rounded border border-gray-200 flex gap-6 text-xs">
            <div><span style={{ color: C.muted }}>Temps exécution : </span><strong>{data.duree}</strong></div>
            <div><span style={{ color: C.muted }}>Gap : </span><strong>{data.paramsUsed.gap.toFixed(3)}%</strong></div>
            <div><span style={{ color: C.muted }}>Campagne active : </span><strong>{data.paramsUsed.campagneActive ? "Oui" : "Non"}</strong></div>
          </div>
          <Card title="Production par famille et semaine (T)">
            <div className="p-4">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={data.weekly} margin={{ top:4, right:16, left:-20, bottom:0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F0F0F0" />
                  <XAxis dataKey="sem" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => `${v.toLocaleString()} T`} />
                  <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="CRC"  fill={FC.CRC}  />
                  <Bar dataKey="HDG"  fill={FC.HDG}  />
                  <Bar dataKey="PPGI" fill={FC.PPGI} />
                  <Bar dataKey="BACR" fill={FC.BACR} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card title="Récapitulatif production">
            <ThTable headers={["Famille","Sem.1 (T)","Sem.2 (T)","Sem.3 (T)","Sem.4 (T)","Total (T)","% total"]}>
              {Object.keys(FC).map((fam, i) => {
                const vals = data.weekly.map(w => (w as Record<string,number>)[fam]||0);
                const tot = vals.reduce((a,b) => a+b, 0);
                const grand = data.weekly.flatMap(w => [w.CRC,w.HDG,w.PPGI,w.BACR]).reduce((a,b)=>a+b,0);
                return (
                  <Tr key={fam} i={i}>
                    <td className="px-3 py-2"><FamilleBadge fam={fam} /></td>
                    {vals.map((v,vi) => <td key={vi} className="px-3 py-2 font-mono tabular-nums">{v.toLocaleString()}</td>)}
                    <td className="px-3 py-2 font-mono font-bold tabular-nums" style={{ color: C.navy }}>{tot.toLocaleString()}</td>
                    <td className="px-3 py-2 font-mono tabular-nums" style={{ color: C.muted }}>{((tot/grand)*100).toFixed(1)}%</td>
                  </Tr>
                );
              })}
            </ThTable>
          </Card>
        </div>
      )}

      {tab === "Commandes" && (
        <Card title="Détail des commandes optimisées">
          <ThTable headers={["ID","Client","Famille","Tonnage (T)","Marge (MDH)","Statut","Sem. Prod."]}>
            {(data.commandesDetail || []).map((c: Commande, i: number) => (
              <Tr key={c.id} i={i}>
                <td className="px-3 py-2 font-mono font-semibold" style={{ color: C.blue }}>{c.id}</td>
                <td className="px-3 py-2" style={{ color: C.navy }}>{c.client}</td>
                <td className="px-3 py-2"><FamilleBadge fam={c.famille} /></td>
                <td className="px-3 py-2 font-mono tabular-nums">{c.ton}</td>
                <td className="px-3 py-2 font-mono font-semibold tabular-nums" style={{ color: c.margeMad >= 0 ? C.green : C.red }}>
                  {(c.margeMad / 1_000_000).toFixed(4)}
                </td>
                <td className="px-3 py-2"><StatutBadge statut={c.statut} /></td>
                <td className="px-3 py-2 font-mono tabular-nums">{c.semProd!=null?`Sem. ${c.semProd}`:"—"}</td>
              </Tr>
            ))}
          </ThTable>
        </Card>
      )}

      {tab === "Marges" && (
        <div className="grid grid-cols-2 gap-3">
          <Card title="Marge par famille (MDH)">
            <div className="p-4">
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie data={data.margeFamily} dataKey="value" cx="50%" cy="50%" innerRadius={55} outerRadius={90} paddingAngle={3}
                    label={({ name, pct }) => `${name} ${pct}%`} labelLine>
                    {data.margeFamily.map((_,i) => <Cell key={i} fill={[C.navy, C.blue, C.orange, C.muted][i]} />)}
                  </Pie>
                  <Tooltip formatter={(v:number) => `${(v * 1_000_000).toLocaleString('fr-FR')} MAD`} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card title="Top commandes par marge">
            <ThTable headers={["Rang","ID","Client","Ton. (T)","Marge (MDH)"]}>
              {(data.commandesDetail || [])
                .filter((c: Commande) => c.statut!=="Refusée")
                .sort((a: Commande,b: Commande) => b.margeMad - a.margeMad)
                .slice(0,8)
                .map((c: Commande, i: number) => (
                  <Tr key={c.id} i={i}>
                    <td className="px-3 py-2 font-mono" style={{ color: C.muted }}>#{i+1}</td>
                    <td className="px-3 py-2 font-mono font-semibold" style={{ color: C.blue }}>{c.id}</td>
                    <td className="px-3 py-2" style={{ color: C.navy }}>{c.client}</td>
                    <td className="px-3 py-2 font-mono tabular-nums">{c.ton}</td>
                    <td className="px-3 py-2 font-mono font-bold tabular-nums" style={{ color: C.green }}>
                      {(c.margeMad / 1_000_000).toFixed(4)}
                    </td>
                  </Tr>
                ))}
            </ThTable>
          </Card>
        </div>
      )}

      {tab === "Utilisation" && (
        <Card title="Taux d'utilisation par ligne et semaine">
          <ThTable headers={["Ligne","Semaine 1","Semaine 2","Semaine 3","Semaine 4","Moyenne"]}>
            {data.lignes.map((row,i) => (
              <Tr key={row.ligne} i={i}>
                <td className="px-3 py-2 font-bold" style={{ color: C.navy }}>{row.ligne}</td>
                {row.s.map((cell,si) => (
                  <td key={si} className="px-3 py-2 text-right">
                    <span className="font-mono text-xs px-1.5 py-0.5 rounded tabular-nums" style={{
                      backgroundColor: cell.p>=100?"#FEF2F2":cell.p>=90?"#FFF7ED":"#ECFDF5",
                      color: cell.p>=100?C.red:cell.p>=90?C.orange:C.green,
                    }}>{cell.p.toFixed(1)}%</span>
                  </td>
                ))}
                <td className="px-3 py-2 text-right">
                  <span className="font-mono text-xs font-bold px-1.5 py-0.5 rounded tabular-nums" style={{
                    backgroundColor: row.moy>=90?"#FEF2F2":row.moy>=80?"#FFF7ED":"#ECFDF5",
                    color: row.moy>=90?C.red:row.moy>=80?C.orange:C.green,
                  }}>{row.moy.toFixed(1)}%</span>
                </td>
              </Tr>
            ))}
          </ThTable>
        </Card>
      )}

      {tab === "B&B" && data.bnbTree && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <KPICard label="Nœuds explorés" value={data.bnbTree.totalLeaves.toString()} Icon={Layers} color={C.blue} />
            <KPICard label="Gap final" value={data.bnbTree.nodes.at(-1)?.gap.toFixed(2) + ' %' || '—'} Icon={Gauge} color={C.orange} />
          </div>

          <Card title="Convergence du gap B&B">
            <div className="p-4">
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={data.bnbTree!.nodes.map(n => ({ noeud: n.nodeId, gap: n.gap }))} margin={{ top:4, right:16, left:-20, bottom:0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F0F0F0" />
                  <XAxis dataKey="noeud" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} domain={[0, 100]} />
                  <Tooltip formatter={(v: number) => `${v.toFixed(2)} %`} />
                  <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="gap" stroke={C.orange} strokeWidth={2} dot={false} name="Gap (%)" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="Évolution des bornes">
            <div className="p-4">
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={data.bnbTree!.nodes.map(n => ({ noeud: n.nodeId, Borne: n.bestBound / 1_000_000, Solution: n.bestInt / 1_000_000 }))} margin={{ top:4, right:16, left:-20, bottom:0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F0F0F0" />
                  <XAxis dataKey="noeud" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip formatter={(v: number) => `${v.toFixed(2)} MDH`} />
                  <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="Borne" stroke={C.blue} strokeWidth={2} dot={false} name="Borne" />
                  <Line type="monotone" dataKey="Solution" stroke={C.green} strokeWidth={2} dot={false} name="Solution" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title={`Détail des nœuds B&B (${totalNodes})`}>
            <div className="overflow-x-auto">
              <ThTable headers={["Nœud","Nœuds restants","Meilleure borne (MDH)","Meilleure solution (MDH)","Gap (%)"]}>
                {pageData.map((n, i) => {
                  const gapColor = n.gap > 5 ? C.red : n.gap > 1 ? C.orange : C.green;
                  return (
                    <Tr key={n.nodeId} i={startIdx + i}>
                      <td className="px-3 py-2 font-mono">{n.nodeId}</td>
                      <td className="px-3 py-2 font-mono">{n.nodesLeft}</td>
                      <td className="px-3 py-2 font-mono">{(n.bestBound / 1_000_000).toFixed(4)}</td>
                      <td className="px-3 py-2 font-mono">{(n.bestInt / 1_000_000).toFixed(4)}</td>
                      <td className="px-3 py-2 font-mono" style={{ color: gapColor }}>{n.gap.toFixed(2)}%</td>
                    </Tr>
                  );
                })}
              </ThTable>
              <div className="flex justify-end gap-2 p-2 text-xs" style={{ color: C.muted }}>
                <button onClick={handlePrev} disabled={pageBNB === 0} className="px-2 py-1 border border-gray-300 rounded disabled:opacity-40">Précédent</button>
                <span>Page {pageBNB+1}/{totalPages}</span>
                <button onClick={handleNext} disabled={pageBNB === totalPages-1} className="px-2 py-1 border border-gray-300 rounded disabled:opacity-40">Suivant</button>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

// ── TÂCHE 2.8 - Sous-composants pour ParametresAvancesCard ──

function OverrideInput({ label, value, onChange, placeholder, unit, originalValue }: {
  label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; unit?: string; originalValue?: string;
}) {
  const isModified = value !== "" && originalValue !== undefined && value !== originalValue;

  return (
    <div>
      <label className="block mb-1 text-xs font-medium" style={{ color: C.muted }}>{label}</label>
      <div className="flex items-center gap-1">
        <input
          type="number"
          step="any"
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder ?? "Valeur Excel"}
          className="w-full border border-gray-200 rounded px-2 py-1.5 text-xs bg-white focus:outline-none focus:border-blue-400"
          style={{ borderColor: isModified ? C.orange : undefined }}
        />
        {unit && <span className="text-xs flex-shrink-0" style={{ color: C.muted }}>{unit}</span>}
      </div>
      {isModified && (
        <p className="text-[10px] mt-0.5" style={{ color: C.orange }}>⚡ Surchargé</p>
      )}
    </div>
  );
}

function OngletEconomique({ overrides, set, originalOverrides }: {
  overrides: OverrideParams;
  set: (field: keyof OverrideParams, val: string) => void;
  originalOverrides: OverrideParams;
}) {
  const fields: Array<{ key: keyof OverrideParams; label: string; unit: string }> = [
    { key: 'prix_zinc', label: 'Prix zinc', unit: 'MAD/T' },
    { key: 'conso_zinc_hdg', label: 'Conso zinc HDG', unit: 'T zinc/T acier' },
    { key: 'conso_zinc_ppgi', label: 'Conso zinc PPGI', unit: 'T zinc/T acier' },
    { key: 'prix_peinture', label: 'Prix peinture', unit: 'MAD/T' },
    { key: 'conso_peinture', label: 'Conso peinture PPGI', unit: 'T peinture/T acier' },
    { key: 'pen_haute', label: 'Pénalité retard Haute', unit: 'MAD/T' },
    { key: 'pen_normale', label: 'Pénalité retard Normale', unit: 'MAD/T' },
    { key: 'pen_basse', label: 'Pénalité retard Basse', unit: 'MAD/T' },
    { key: 'cout_stock_inter', label: 'Coût stock interprocess', unit: 'MAD/T/sem' },
    { key: 'cout_stock_fini', label: 'Coût stock produit fini', unit: 'MAD/T/sem' },
    { key: 'prix_chute', label: 'Prix valorisation chutes', unit: 'MAD/T' },
    { key: 'coef_decl', label: 'Coef. déclassé', unit: '' },
    { key: 'coef_nc', label: 'Coef. non-conforme', unit: '' },
  ];
  return (
    <div className="grid grid-cols-3 gap-4">
      {fields.map(f => (
        <OverrideInput
          key={f.key}
          label={f.label}
          value={overrides[f.key] as string}
          onChange={v => set(f.key, v)}
          unit={f.unit}
          originalValue={originalOverrides[f.key] as string}
        />
      ))}
    </div>
  );
}

function OngletStocks({ overrides, setOverrides, originalOverrides }: {
  overrides: OverrideParams;
  setOverrides: (o: OverrideParams) => void;
  originalOverrides: OverrideParams;
}) {
  const updateStockPk = (grade: string, field: keyof StockOverride, val: string) => {
    const num = val === "" ? undefined : Number(val);
    setOverrides({
      ...overrides,
      stock_pk: {
        ...overrides.stock_pk,
        [grade]: { ...overrides.stock_pk[grade], [field]: num }
      }
    });
  };

  const updateStockInter = (point: string, field: keyof StockOverride, val: string) => {
    const num = val === "" ? undefined : Number(val);
    setOverrides({
      ...overrides,
      stock_inter: {
        ...overrides.stock_inter,
        [point]: { ...overrides.stock_inter[point], [field]: num }
      }
    });
  };

  const updateStockFini = (famille: string, field: keyof StockOverride, val: string) => {
    const num = val === "" ? undefined : Number(val);
    setOverrides({
      ...overrides,
      stock_fini: {
        ...overrides.stock_fini,
        [famille]: { ...overrides.stock_fini[famille], [field]: num }
      }
    });
  };

  const renderTable = (title: string, rows: Array<{ key: string; label: string }>,
    getter: (key: string) => StockOverride,
    updater: (key: string, field: keyof StockOverride, val: string) => void,
    originalGetter: (key: string) => StockOverride) => {
    return (
      <div className="mb-6">
        <h4 className="text-xs font-semibold uppercase mb-2" style={{ color: C.muted }}>{title}</h4>
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-100">
              <th className="text-left px-2 py-1">Item</th>
              <th className="text-left px-2 py-1">Stock init (T)</th>
              <th className="text-left px-2 py-1">Stock min (T)</th>
              <th className="text-left px-2 py-1">Stock max (T)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({key, label}) => {
              const data = getter(key);
              const orig = originalGetter(key);
              return (
                <tr key={key} className="border-b border-gray-50">
                  <td className="px-2 py-1 font-medium" style={{ color: C.navy }}>{label}</td>
                  <td className="px-2 py-1">
                    <input
                      type="number"
                      step="any"
                      value={data.init !== undefined ? data.init : ''}
                      onChange={e => updater(key, 'init', e.target.value)}
                      placeholder="Excel"
                      className="w-20 border border-gray-200 rounded px-1.5 py-0.5 text-xs bg-white focus:outline-none focus:border-blue-400"
                      style={{ borderColor: (data.init !== undefined && orig?.init !== undefined && data.init !== orig.init) ? C.orange : undefined }}
                    />
                    {data.init !== undefined && orig?.init !== undefined && data.init !== orig.init && (
                      <span className="ml-1 text-[10px]" style={{ color: C.orange }}>⚡</span>
                    )}
                  </td>
                  <td className="px-2 py-1">
                    <input
                      type="number"
                      step="any"
                      value={data.min !== undefined ? data.min : ''}
                      onChange={e => updater(key, 'min', e.target.value)}
                      placeholder="Excel"
                      className="w-20 border border-gray-200 rounded px-1.5 py-0.5 text-xs bg-white focus:outline-none focus:border-blue-400"
                      style={{ borderColor: (data.min !== undefined && orig?.min !== undefined && data.min !== orig.min) ? C.orange : undefined }}
                    />
                    {data.min !== undefined && orig?.min !== undefined && data.min !== orig.min && (
                      <span className="ml-1 text-[10px]" style={{ color: C.orange }}>⚡</span>
                    )}
                  </td>
                  <td className="px-2 py-1">
                    <input
                      type="number"
                      step="any"
                      value={data.max !== undefined ? data.max : ''}
                      onChange={e => updater(key, 'max', e.target.value)}
                      placeholder="Excel"
                      className="w-20 border border-gray-200 rounded px-1.5 py-0.5 text-xs bg-white focus:outline-none focus:border-blue-400"
                      style={{ borderColor: (data.max !== undefined && orig?.max !== undefined && data.max !== orig.max) ? C.orange : undefined }}
                    />
                    {data.max !== undefined && orig?.max !== undefined && data.max !== orig.max && (
                      <span className="ml-1 text-[10px]" style={{ color: C.orange }}>⚡</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  };

  const pkRows = [
    { key: 'DC01', label: 'DC01' },
    { key: 'DD13', label: 'DD13' },
    { key: 'DX51', label: 'DX51' },
    { key: 'DX52', label: 'DX52' },
    { key: 'S320', label: 'S320' },
  ];
  const interRows = [
    { key: 'FH-CRMA', label: 'FH-CRMA' },
    { key: 'FH-CRMB', label: 'FH-CRMB' },
    { key: 'BAF-out', label: 'BAF-out' },
    { key: 'SKP-out', label: 'SKP-out' },
  ];
  const finiRows = [
    { key: 'CRC', label: 'CRC' },
    { key: 'HDG', label: 'HDG' },
    { key: 'PPGI', label: 'PPGI' },
    { key: 'BACR', label: 'BACR' },
  ];

  return (
    <div>
      {renderTable('Stock PK', pkRows, k => overrides.stock_pk[k] || {}, updateStockPk, k => originalOverrides.stock_pk[k] || {})}
      {renderTable('Stock interprocess', interRows, k => overrides.stock_inter[k] || {}, updateStockInter, k => originalOverrides.stock_inter[k] || {})}
      {renderTable('Stock produits finis', finiRows, k => overrides.stock_fini[k] || {}, updateStockFini, k => originalOverrides.stock_fini[k] || {})}
    </div>
  );
}

function OngletDispoHRC({ overrides, setOverrides, originalOverrides }: {
  overrides: OverrideParams;
  setOverrides: (o: OverrideParams) => void;
  originalOverrides: OverrideParams;
}) {
  const grades = ['DC01', 'DD13', 'DX51', 'DX52', 'S320'];
  return (
    <div className="grid grid-cols-5 gap-4">
      {grades.map(g => (
        <OverrideInput
          key={g}
          label={g}
          value={overrides.dispo_hrc[g] || ''}
          onChange={v => setOverrides({
            ...overrides,
            dispo_hrc: { ...overrides.dispo_hrc, [g]: v }
          })}
          unit="T"
          originalValue={originalOverrides.dispo_hrc[g] || ''}
        />
      ))}
    </div>
  );
}

function OngletArrets({ overrides, setOverrides, originalOverrides }: {
  overrides: OverrideParams;
  setOverrides: (o: OverrideParams) => void;
  originalOverrides: OverrideParams;
}) {
  const machines = ['PK', 'CRMA', 'CRMB', 'BAF', 'SKP', 'LGA', 'LGB'];
  const semaines = [1, 2, 3, 4];
  const joursSemaine = 7;

  const getValue = (mach: string, sem: number) => overrides.arrets[`${mach}-S${sem}`] || '';
  const getOriginalValue = (mach: string, sem: number) => originalOverrides.arrets[`${mach}-S${sem}`] || '';
  const setValue = (mach: string, sem: number, val: string) => {
    if (val !== '') {
      const num = Number(val);
      if (isNaN(num) || num < 0 || num > joursSemaine) {
        alert(`La valeur doit être comprise entre 0 et ${joursSemaine} jours.`);
        return;
      }
    }
    const key = `${mach}-S${sem}`;
    setOverrides({
      ...overrides,
      arrets: { ...overrides.arrets, [key]: val }
    });
  };

  return (
    <div>
      <p className="text-xs mb-2" style={{ color: C.muted }}>
        Arrêts planifiés (en JOURS d'arrêt sur une semaine de {joursSemaine} jours ouvrés)
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-100">
              <th className="text-left px-2 py-1">Machine</th>
              {semaines.map(s => (
                <th key={s} className="text-center px-2 py-1">Semaine {s}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {machines.map(mach => (
              <tr key={mach} className="border-b border-gray-50">
                <td className="px-2 py-1 font-medium" style={{ color: C.navy }}>{mach}</td>
                {semaines.map(s => {
                  const val = getValue(mach, s);
                  const orig = getOriginalValue(mach, s);
                  const isModified = val !== "" && orig !== "" && val !== orig;
                  return (
                    <td key={s} className="px-2 py-1 text-center">
                      <input
                        type="number"
                        step="any"
                        min="0"
                        max={joursSemaine}
                        value={val}
                        onChange={e => setValue(mach, s, e.target.value)}
                        placeholder="0j"
                        className="w-16 border border-gray-200 rounded px-1.5 py-0.5 text-xs bg-white focus:outline-none focus:border-blue-400 text-center"
                        style={{ borderColor: isModified ? C.orange : undefined }}
                      />
                      {isModified && <span className="ml-1 text-[10px]" style={{ color: C.orange }}>⚡</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
// ── Fonction de comparaison des overrides ──
function getOverridesDifferences(overrides: OverrideParams, originalOverrides: OverrideParams): string[] {
  const diffs: string[] = [];

  // 1. Paramètres économiques scalaires
  const scalarKeys: (keyof OverrideParams)[] = [
    'prix_zinc', 'conso_zinc_hdg', 'conso_zinc_ppgi', 'prix_peinture', 'conso_peinture',
    'pen_haute', 'pen_normale', 'pen_basse', 'cout_stock_inter', 'cout_stock_fini',
    'prix_chute', 'coef_decl', 'coef_nc'
  ];
  for (const key of scalarKeys) {
    const current = overrides[key] as string;
    const original = originalOverrides[key] as string;
    if (current !== original && current !== "") {
      diffs.push(`${key} : ${original || "(vide)"} → ${current}`);
    }
  }

  // 2. Stock PK (grade)
  for (const grade of Object.keys(overrides.stock_pk)) {
    const cur = overrides.stock_pk[grade];
    const orig = originalOverrides.stock_pk[grade] || {};
    for (const field of ['init', 'min', 'max'] as const) {
      const curVal = cur[field];
      const origVal = orig[field];
      if (curVal !== undefined && curVal !== origVal) {
        diffs.push(`stock_pk.${grade}.${field} : ${origVal ?? "(vide)"} → ${curVal}`);
      }
    }
  }

  // 3. Stock interprocess
  for (const point of Object.keys(overrides.stock_inter)) {
    const cur = overrides.stock_inter[point];
    const orig = originalOverrides.stock_inter[point] || {};
    for (const field of ['init', 'min', 'max'] as const) {
      const curVal = cur[field];
      const origVal = orig[field];
      if (curVal !== undefined && curVal !== origVal) {
        diffs.push(`stock_inter.${point}.${field} : ${origVal ?? "(vide)"} → ${curVal}`);
      }
    }
  }

  // 4. Stock fini
  for (const famille of Object.keys(overrides.stock_fini)) {
    const cur = overrides.stock_fini[famille];
    const orig = originalOverrides.stock_fini[famille] || {};
    for (const field of ['init', 'min', 'max'] as const) {
      const curVal = cur[field];
      const origVal = orig[field];
      if (curVal !== undefined && curVal !== origVal) {
        diffs.push(`stock_fini.${famille}.${field} : ${origVal ?? "(vide)"} → ${curVal}`);
      }
    }
  }

  // 5. Disponibilité HRC
  for (const grade of Object.keys(overrides.dispo_hrc)) {
    const cur = overrides.dispo_hrc[grade];
    const orig = originalOverrides.dispo_hrc[grade] || "";
    if (cur !== orig && cur !== "") {
      diffs.push(`dispo_hrc.${grade} : ${orig || "(vide)"} → ${cur}`);
    }
  }

  // 6. Arrêts planifiés
  for (const key of Object.keys(overrides.arrets)) {
    const cur = overrides.arrets[key];
    const orig = originalOverrides.arrets[key] || "";
    if (cur !== orig && cur !== "") {
      diffs.push(`arrets.${key} : ${orig || "(vide)"} → ${cur}`);
    }
  }

  return diffs;
}

// --- TÂCHE 2.7 - ParametresAvancesCard ---
function ParametresAvancesCard({
  overrides, setOverrides, originalOverrides
}: {
  overrides: OverrideParams;
  setOverrides: (o: OverrideParams) => void;
  originalOverrides: OverrideParams;
}) {
  const [tab, setTab] = useState<'eco' | 'stocks' | 'hrc' | 'arrets'>('eco');

  const set = (field: keyof OverrideParams, val: string) =>
    setOverrides({ ...overrides, [field]: val });

  const reset = () => setOverrides(originalOverrides);

  return (
    <Card title="Paramètres avancés (surcharges)" action={
      <button onClick={reset} className="text-xs flex items-center gap-1 px-2 py-1 rounded border border-red-200 text-red-500 hover:bg-red-50">
        <RefreshCw size={10} /> Réinitialiser
      </button>
    }>
      <div className="px-4 pt-3 flex gap-1 border-b border-gray-100">
        {([['eco','Économique'],['stocks','Stocks initiaux'],['hrc','Dispo HRC'],['arrets','Arrêts']] as const).map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            className="text-xs px-3 py-1.5 rounded-t transition-all"
            style={{
              backgroundColor: tab === id ? C.navy : 'transparent',
              color: tab === id ? 'white' : C.muted,
              fontWeight: tab === id ? 600 : 400,
            }}>
            {label}
          </button>
        ))}
      </div>

      <div className="p-4">
        {tab === 'eco' && <OngletEconomique overrides={overrides} set={set} originalOverrides={originalOverrides} />}
        {tab === 'stocks' && <OngletStocks overrides={overrides} setOverrides={setOverrides} originalOverrides={originalOverrides} />}
        {tab === 'hrc' && <OngletDispoHRC overrides={overrides} setOverrides={setOverrides} originalOverrides={originalOverrides} />}
        {tab === 'arrets' && <OngletArrets overrides={overrides} setOverrides={setOverrides} originalOverrides={originalOverrides} />}
      </div>
    </Card>
  );
}

// --- ScenariosPage ---
function ScenariosPage({
  imports,
  activeImportId,
  setActiveImportId,
  simParams,
  setSimParams,
  onLaunch,
  running,
  progress,
  uploadedFileUrl,
  uploadedFileName,
  onUpload,
  overrides,
  setOverrides,
  loadingParams,
}: {
  imports: ImportSession[];
  activeImportId: string | null;
  setActiveImportId: (id: string) => void;
  simParams: SimParams;
  setSimParams: (p: SimParams) => void;
  onLaunch: () => void;
  running: boolean;
  progress: number;
  uploadedFileUrl: string | null;
  uploadedFileName: string | null;
  onUpload: (file: File) => void;
  overrides: OverrideParams;
  setOverrides: (o: OverrideParams) => void;
  loadingParams: boolean;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const handleUploadClick = () => fileInputRef.current?.click();
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) onUpload(file);
    e.target.value = '';
  };

  const activeImport = imports.find(i => i.id === activeImportId);
  const originalOverrides = activeImport?.overridesData || DEFAULT_OVERRIDES;

  // Ne dépendre que de activeImportId et activeImport, pas de setOverrides (stable)
  useEffect(() => {
    if (activeImportId && activeImport?.overridesData) {
      setOverrides(activeImport.overridesData);
    }
  }, [activeImportId, activeImport]); // setOverrides est stable, on ne le met pas

  return (
    <div className="space-y-3">
      <Card title="Importer des commandes depuis Excel" action={
        <button onClick={handleUploadClick} className="text-xs px-3 py-1.5 rounded text-white flex items-center gap-1.5 hover:opacity-90" style={{ backgroundColor: C.blue }}>
          <Upload size={10} /> Choisir un fichier
        </button>
      }>
        <div className="p-4 flex flex-col gap-3">
          <input type="file" ref={fileInputRef} accept=".xlsx,.xls" style={{ display: 'none' }} onChange={handleFileChange} />
          
          {!uploadedFileName && (
            <span style={{ color: C.muted }}>
              Chargez un fichier Excel (feuille "Commandes") pour créer un scénario.
            </span>
          )}

          {uploadedFileName && (
            <div className="flex items-center gap-3 p-3 bg-green-50 border border-green-200 rounded">
              <CheckCircle2 size={14} style={{ color: C.green }} />
              <span className="text-sm font-medium" style={{ color: C.navy }}>{uploadedFileName}</span>
              {loadingParams && <span className="text-xs text-blue-600">Lecture des paramètres...</span>}
              <a href={uploadedFileUrl!} download={uploadedFileName}
                 className="text-xs px-2 py-1 rounded border border-blue-300 text-blue-600 hover:bg-blue-50 ml-auto">
                Télécharger le fichier
              </a>
            </div>
          )}
        </div>
      </Card>

      <Card title="Paramètres de la simulation">
        <div className="p-4 space-y-4">
          <div className="grid grid-cols-4 gap-4">
            <div>
              <label className="block mb-1.5 font-medium text-xs" style={{ color: C.muted }}>Fichier actif</label>
              <select
                className="w-full border border-gray-200 rounded px-2 py-1.5 bg-white focus:outline-none focus:border-blue-400 text-xs"
                value={activeImportId || ''}
                onChange={e => setActiveImportId(e.target.value)}
              >
                <option value="">-- Aucun --</option>
                {imports.map(i => (
                  <option key={i.id} value={i.id}>{i.fileName}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block mb-1.5 font-medium text-xs" style={{ color: C.muted }}>Début de l'horizon</label>
              <input type="text" value="05/05/2026" disabled className="w-full border border-gray-200 rounded px-2 py-1.5 bg-gray-100 text-gray-500 text-xs" />
            </div>
            <div>
              <label className="block mb-1.5 font-medium text-xs" style={{ color: C.muted }}>Nombre de semaines</label>
              <input type="text" value="4 semaines" disabled className="w-full border border-gray-200 rounded px-2 py-1.5 bg-gray-100 text-gray-500 text-xs" />
            </div>
            <div>
              <label className="block mb-1.5 font-medium text-xs" style={{ color: C.muted }}>Gap (tolérance)</label>
              <input
                type="number"
                step="0.1"
                min="0"
                value={simParams.gap}
                onChange={e => setSimParams({ ...simParams, gap: parseFloat(e.target.value) || 0 })}
                className="w-full border border-gray-200 rounded px-2 py-1.5 bg-white focus:outline-none focus:border-blue-400 text-xs"
              />
            </div>
          </div>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-1.5 text-xs" style={{ color: C.muted }}>
              <input
                type="checkbox"
                checked={simParams.campagneActive}
                onChange={e => setSimParams({ ...simParams, campagneActive: e.target.checked })}
              />
              Campagne active
            </label>
            <label className="flex items-center gap-1.5 text-xs" style={{ color: C.muted }}>
              <input
                type="checkbox"
                checked={simParams.activerB2}
                onChange={e => setSimParams({ ...simParams, activerB2: e.target.checked })}
              />
              Activer B2 (retards)
            </label>
          </div>

          <div className="flex gap-3">
            <button
              onClick={onLaunch}
              disabled={running || !activeImportId}
              className="px-4 py-1.5 rounded text-white text-xs font-semibold flex items-center gap-1.5 hover:opacity-90 disabled:opacity-60"
              style={{ backgroundColor: C.orange }}
            >
              <Play size={12} />
              {running ? `Simulation en cours… ${progress}%` : "Lancer la simulation"}
            </button>
            {running && (
              <div className="flex-1 bg-gray-200 rounded-full h-1.5 my-auto">
                <div className="h-1.5 rounded-full transition-all" style={{ width:`${progress}%`, backgroundColor: C.orange }} />
              </div>
            )}
          </div>
        </div>
      </Card>

      <ParametresAvancesCard
        overrides={overrides}
        setOverrides={setOverrides}
        originalOverrides={originalOverrides}
      />
    </div>
  );
}

// --- HistoriquePage ---
function HistoriquePage({ imports, runs, onSelectRun, onSaveRun, onDeleteRun, compareIds, toggleCompare, onCompare }: {
  imports: ImportSession[];
  runs: RunResult[];
  onSelectRun: (id: number) => void;
  onSaveRun: (id: number) => void;
  onDeleteRun: (id: number) => void;
  compareIds: number[];
  toggleCompare: (id: number) => void;
  onCompare: () => void;
}) {
  const [fileFilter, setFileFilter] = useState<string>('Tous');
  const [typeFilter, setTypeFilter] = useState<string>('Tous');
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

  const toggleExpand = (runId: number) => {
    const newSet = new Set(expandedRows);
    if (newSet.has(runId)) {
      newSet.delete(runId);
    } else {
      newSet.add(runId);
    }
    setExpandedRows(newSet);
  };

  const filteredRuns = runs.filter(r => {
    const imp = imports.find(i => i.id === r.importId);
    if (fileFilter !== 'Tous' && imp?.fileName !== fileFilter) return false;
    if (typeFilter !== 'Tous' && r.runType !== typeFilter) return false;
    return true;
  });

  const grouped = imports.map(imp => ({
    ...imp,
    runs: filteredRuns.filter(r => r.importId === imp.id)
  })).filter(g => g.runs.length > 0);

  return (
    <div className="space-y-4">
      <div className="bg-white border border-gray-200 rounded p-3 flex items-center gap-3 flex-wrap">
        <span className="text-xs font-medium" style={{ color: C.muted }}>Filtres :</span>
        <select className="text-xs border border-gray-200 rounded px-2 py-1 bg-white focus:outline-none" value={fileFilter} onChange={e => setFileFilter(e.target.value)}>
          <option value="Tous">Tous les fichiers</option>
          {imports.map(i => <option key={i.id} value={i.fileName}>{i.fileName}</option>)}
        </select>
        <select className="text-xs border border-gray-200 rounded px-2 py-1 bg-white focus:outline-none" value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
          <option value="Tous">Tous les types</option>
          <option value="base">Base</option>
          <option value="personnalise">Personnalisé</option>
        </select>
        <span className="ml-auto text-xs" style={{ color: C.muted }}>{filteredRuns.length} runs</span>
        {compareIds.length > 0 && (
          <button
            className="text-xs px-2 py-1 rounded bg-blue-100 text-blue-700"
            onClick={onCompare}
          >
            Comparer ({compareIds.length})
          </button>
        )}
      </div>

      {grouped.map(group => {
        const originalOverrides = group.overridesData || DEFAULT_OVERRIDES;

        return (
          <Card key={group.id} title={`📁 ${group.fileName}`}>
            <div className="px-3 py-1 text-xs" style={{ color: C.muted }}>
              Importé le {group.importedAt}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100">
                    <th className="text-left px-3 py-2 font-semibold uppercase tracking-wide" style={{ color: C.muted }}> </th>
                    <th className="text-left px-3 py-2 font-semibold uppercase tracking-wide" style={{ color: C.muted }}>Run</th>
                    <th className="text-left px-3 py-2 font-semibold uppercase tracking-wide" style={{ color: C.muted }}>Type</th>
                    <th className="text-left px-3 py-2 font-semibold uppercase tracking-wide" style={{ color: C.muted }}>Campagne</th>
                    <th className="text-left px-3 py-2 font-semibold uppercase tracking-wide" style={{ color: C.muted }}>Surcharges</th>
                    <th className="text-right px-3 py-2 font-semibold uppercase tracking-wide" style={{ color: C.muted }}>Marge (MDH)</th>
                    <th className="text-right px-3 py-2 font-semibold uppercase tracking-wide" style={{ color: C.muted }}>Gap</th>
                    <th className="text-left px-3 py-2 font-semibold uppercase tracking-wide" style={{ color: C.muted }}>Date</th>
                    <th className="text-left px-3 py-2 font-semibold uppercase tracking-wide" style={{ color: C.muted }}>Sauvegardé</th>
                    <th className="text-left px-3 py-2 font-semibold uppercase tracking-wide" style={{ color: C.muted }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {group.runs.map((r, i) => {
                    const overrides = r.paramsUsed.overrides || DEFAULT_OVERRIDES;
                    const diffs = getOverridesDifferences(overrides, originalOverrides);
                    const nbSurcharges = diffs.length;
                    const isExpanded = expandedRows.has(r.id);

                    return (
                      <React.Fragment key={r.id}>
                        <tr className={`border-b border-gray-50 hover:bg-blue-50/20 transition-colors ${i % 2 !== 0 ? "bg-gray-50/40" : ""}`}>
                          <td className="px-3 py-2">
                            <input type="checkbox" checked={compareIds.includes(r.id)} onChange={() => toggleCompare(r.id)} />
                          </td>
                          <td className="px-3 py-2 font-medium">{r.label}</td>
                          <td className="px-3 py-2">
                            <Badge
                              label={r.runType === 'base' ? 'Base' : 'Personnalisé'}
                              bg={r.runType === 'base' ? '#ECFDF5' : '#EFF6FF'}
                              text={r.runType === 'base' ? C.green : C.blue}
                            />
                          </td>
                          <td className="px-3 py-2">{r.paramsUsed.campagneActive ? 'Oui' : 'Non'}</td>
                          <td className="px-3 py-2">
                            {nbSurcharges > 0 ? (
                              <div className="flex items-center gap-1">
                                <Badge
                                  label={`${nbSurcharges} modif(s)`}
                                  bg="#FFF7ED"
                                  text={C.orange}
                                />
                                <button
                                  onClick={() => toggleExpand(r.id)}
                                  className="text-xs text-blue-600 hover:text-blue-800 focus:outline-none"
                                >
                                  {isExpanded ? '▲' : '▼'}
                                </button>
                              </div>
                            ) : (
                              <span style={{ color: C.muted }}>—</span>
                            )}
                          </td>
                          <td className="px-3 py-2 font-mono text-right">{r.marge.toFixed(2)}</td>
                          <td className="px-3 py-2 font-mono text-right">{r.paramsUsed.gap.toFixed(3)}%</td>
                          <td className="px-3 py-2 font-mono">{r.executedAt}</td>
                          <td className="px-3 py-2">
                            {r.saved
                              ? <Badge label="Enregistré" bg="#ECFDF5" text={C.green} />
                              : <button onClick={() => onSaveRun(r.id)} className="text-xs px-2 py-0.5 rounded border border-gray-200 hover:bg-gray-50">
                                  Enregistrer
                                </button>}
                          </td>
                          <td className="px-3 py-2 flex gap-1">
                            <button onClick={() => onSelectRun(r.id)} className="text-xs px-2 py-0.5 rounded text-white" style={{ backgroundColor: C.blue }}>
                              Consulter
                            </button>
                            <button
                              onClick={() => onDeleteRun(r.id)}
                              className="text-xs px-2 py-0.5 rounded border border-red-200 text-red-600 hover:bg-red-50 transition-colors"
                              title="Supprimer cette simulation"
                            >
                              <Trash2 size={10} />
                            </button>
                          </td>
                        </tr>
                        {isExpanded && nbSurcharges > 0 && (
                          <tr>
                            <td colSpan={10} style={{ backgroundColor: '#FFFAF0', borderBottom: `1px solid ${C.border}` }}>
                              <div className="px-6 py-3">
                                <p className="font-semibold text-xs mb-2" style={{ color: C.navy }}>Modifications apportées :</p>
                                <ul className="list-disc pl-5 space-y-1 text-xs" style={{ color: C.navy }}>
                                  {diffs.map((diff, idx) => (
                                    <li key={idx} style={{ fontFamily: 'monospace' }}>{diff}</li>
                                  ))}
                                </ul>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        );
      })}

      {grouped.length === 0 && (
        <div className="text-center py-8" style={{ color: C.muted }}>
          Aucun historique pour le moment. Importez un fichier et lancez une simulation.
        </div>
      )}
    </div>
  );
}
//--- ComparateurPage ---
function ComparateurPage({ runs, compareIds }: { runs: RunResult[]; compareIds: number[] }) {
  const selected = runs.filter(r => compareIds.includes(r.id));

  if (compareIds.length === 0 || selected.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64" style={{ color: C.muted }}>
        <AlertCircle size={32} className="mb-2" />
        <p className="text-lg font-semibold">Aucun scénario sélectionné</p>
        <p className="text-sm">Retournez sur la page Historique et cochez les scénarios à comparer.</p>
      </div>
    );
  }

  const metrics: { key: keyof RunResult; label: string; fmt: (v: any) => string }[] = [
    { key: 'marge',                    label: 'Marge (MAD)',            fmt: v => (v * 1_000_000).toLocaleString('fr-FR') },
    { key: 'duree',                    label: 'Temps d\'exécution',     fmt: v => v },
    { key: 'tauxService',              label: 'Taux de service (%)',    fmt: v => v.toFixed(1) },
    { key: 'commandesRefuseesCount',   label: 'Commandes refusées',     fmt: v => String(v) },
    { key: 'commandesRefuseesTonnage', label: 'Tonnage refusé (T)',     fmt: v => v.toLocaleString() },
    { key: 'utilisationMoyenne',       label: 'Utilisation moyenne (%)',fmt: v => v.toFixed(1) },
  ];

  const barData = selected.map(r => ({
    label: r.label,
    marge: r.marge,
    tauxService: r.tauxService,
  }));

  return (
    <div className="space-y-4">
      <Card title={`Comparaison (${selected.length} runs)`}>
        <div className="p-4">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={barData} margin={{ top:4, right:16, left:-20, bottom:0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F0F0F0" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="marge" fill={C.blue} name="Marge (MDH)" />
              <Bar dataKey="tauxService" fill={C.green} name="Taux service (%)" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <table className="w-full text-xs">
          <thead>
            <tr><th className="text-left px-3 py-2">Métrique</th>
              {selected.map(r => <th key={r.id} className="px-3 py-2">{r.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {metrics.map(m => (
              <tr key={m.key as string} className="border-t border-gray-100">
                <td className="px-3 py-2 font-medium" style={{ color: C.muted }}>{m.label}</td>
                {selected.map(r => (
                  <td key={r.id} className="px-3 py-2 font-mono text-center">{m.fmt(r[m.key])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ── Navigation ───────────────────────────────────────────────────────────────

const NAV = [
  { id:"dashboard",    label:"Tableau de bord", Icon: LayoutDashboard },
  { id:"commandes",    label:"Commandes",       Icon: ShoppingCart    },
  { id:"plan",         label:"Plan de marche",  Icon: Map             },
  { id:"plan_production", label:"Plan de production", Icon: ClipboardList },
  { id:"stocks",       label:"Stocks",          Icon: Package2        },
  { id:"resultats",    label:"Résultats",       Icon: BarChart3       },
  { id:"scenarios",    label:"Scénarios",       Icon: GitCompare      },
  { id:"historique",   label:"Historique",      Icon: History         },
  { id:"comparaison",  label:"Comparaison",     Icon: GitCompare      },
] as const;

type PageId = typeof NAV[number]["id"];

// ── App ──────────────────────────────────────────────────────────────────────

const API_URL = 'http://localhost:5000/optimize';
const API_BASE = 'http://localhost:5000';

const LS_KEY_IMPORTS = 'maghreb_steel_imports';
const LS_KEY_ACTIVE_RUN = 'maghreb_steel_active_run';
const LS_KEY_PAGE = 'maghreb_steel_page';

export default function App() {
  const [imports, setImports] = useState<ImportSession[]>(() => {
    const stored = localStorage.getItem(LS_KEY_IMPORTS);
    if (stored) {
      try { return JSON.parse(stored); } catch { /* ignore */ }
    }
    return [];
  });

  const [runs, setRuns] = useState<RunResult[]>([]);
  const [simParams, setSimParams] = useState<SimParams>({
    gap: 0.5,
    campagneActive: true,
    activerB2: true,
    overrides: DEFAULT_OVERRIDES,
  });
  const [activeRunId, setActiveRunId] = useState<number | null>(() => {
    const stored = localStorage.getItem(LS_KEY_ACTIVE_RUN);
    return stored ? Number(stored) : null;
  });
  const [activeImportId, setActiveImportId] = useState<string | null>(null);

  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [uploadedFileUrl, setUploadedFileUrl] = useState<string | null>(null);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);

  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);

  const [page, setPage] = useState<PageId>(() => {
    const stored = localStorage.getItem(LS_KEY_PAGE) as PageId | null;
    return stored && NAV.some(n => n.id === stored) ? stored : "dashboard";
  });

  const [compareIds, setCompareIds] = useState<number[]>([]);

  const [sidebarWidth, setSidebarWidth] = useState<number>(208);
  const [isHoverConfig, setIsHoverConfig] = useState(false);

  const [isLoadingRuns, setIsLoadingRuns] = useState(true);
  const [loadingParams, setLoadingParams] = useState(false);

  const activeRun = runs.find(r => r.id === activeRunId) ?? null;

  // ── Stabiliser les fonctions avec useCallback ──────────────────────
  const handleSetOverrides = useCallback((o: OverrideParams) => {
    setSimParams(prev => ({ ...prev, overrides: o }));
  }, []);

  const handleSetSimParams = useCallback((p: SimParams) => {
    setSimParams(p);
  }, []);

  // Persistance
  useEffect(() => {
    localStorage.setItem(LS_KEY_IMPORTS, JSON.stringify(imports));
  }, [imports]);

  useEffect(() => {
    if (activeRunId !== null) {
      localStorage.setItem(LS_KEY_ACTIVE_RUN, String(activeRunId));
    } else {
      localStorage.removeItem(LS_KEY_ACTIVE_RUN);
    }
  }, [activeRunId]);

  useEffect(() => {
    localStorage.setItem(LS_KEY_PAGE, page);
  }, [page]);

  // Charger les runs sauvegardés
  useEffect(() => {
    const fetchSaved = async () => {
      try {
        const res = await fetch(`${API_BASE}/runs`);
        if (!res.ok) return;
        const saved = await res.json();
        if (saved.length > 0) {
          setRuns(prev => {
            const existingIds = new Set(prev.map(r => r.id));
            const newRuns = saved.filter((r: RunResult) => !existingIds.has(r.id));
            const allRuns = [...prev, ...newRuns];
            if (activeRunId !== null && !allRuns.some(r => r.id === activeRunId)) {
              setActiveRunId(null);
              localStorage.removeItem(LS_KEY_ACTIVE_RUN);
            }
            return allRuns;
          });
        } else {
          if (activeRunId !== null) {
            setActiveRunId(null);
            localStorage.removeItem(LS_KEY_ACTIVE_RUN);
          }
        }
      } catch (e) {
        console.warn('Impossible de charger les runs sauvegardés', e);
      } finally {
        setIsLoadingRuns(false);
      }
    };
    fetchSaved();
  }, []);

  // ── Fonction d'upload ──────────────────────────────────────────────
  const handleUpload = async (file: File) => {
    setLoadingParams(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await fetch(`${API_BASE}/lire-parametres-fichier`, {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.error || 'Erreur lors de la lecture du fichier');
      }
      const overridesData: OverrideParams = await response.json();

      const imp: ImportSession = {
        id: `imp_${Date.now()}`,
        fileName: file.name,
        importedAt: new Date().toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }),
        overridesData: overridesData,
      };
      setImports(prev => [...prev, imp]);
      setActiveImportId(imp.id);
      setUploadedFileName(file.name);
      setUploadedFileUrl(URL.createObjectURL(file));
      setUploadedFile(file);

      handleSetOverrides(overridesData);
    } catch (err) {
      alert('Erreur lors de l\'import : ' + (err as Error).message);
    } finally {
      setLoadingParams(false);
    }
  };

  const handleSaveRun = async (runId: number) => {
    const run = runs.find(r => r.id === runId);
    if (!run) return;
    try {
      await fetch(`${API_BASE}/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(run),
      });
      setRuns(prev => prev.map(r => r.id === runId ? { ...r, saved: true } : r));
      
      if (run.exportFile) {
        const link = document.createElement('a');
        link.href = `${API_BASE}/download/${run.exportFile}`;
        link.download = run.exportFile;
        link.click();
      } else {
        alert('Aucun fichier Excel disponible pour ce run.');
      }
    } catch (e) {
      alert('Erreur lors de la sauvegarde');
    }
  };

  const handleDeleteRun = async (runId: number) => {
    if (!window.confirm('Êtes-vous sûr de vouloir supprimer cette simulation ?')) return;
    try {
      const res = await fetch(`${API_BASE}/runs/${runId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Erreur lors de la suppression');
      setRuns(prev => prev.filter(r => r.id !== runId));
      if (activeRunId === runId) {
        setActiveRunId(null);
        localStorage.removeItem(LS_KEY_ACTIVE_RUN);
      }
    } catch (e) {
      alert('Erreur lors de la suppression');
    }
  };

  const handleLaunch = () => {
    const imp = imports.find(i => i.id === activeImportId);
    if (!imp) {
      alert('Veuillez d\'abord importer un fichier Excel.');
      return;
    }
    if (!uploadedFile) {
      alert('Le fichier n\'est plus disponible. Veuillez le réimporter.');
      return;
    }
    runOptimization({ ...imp, file: uploadedFile });
  };

  const runOptimization = async (imp: ImportSession & { file: File }) => {
    const formData = new FormData();
    formData.append('file', imp.file);
    formData.append('activer_B2', String(simParams.activerB2));
    formData.append('activer_B4', String(simParams.campagneActive));
    formData.append('gap', String(simParams.gap));
    formData.append('overrides', JSON.stringify(simParams.overrides));

    setRunning(true);
    setProgress(0);

    try {
      const startRes = await fetch(API_URL, {
        method: 'POST',
        body: formData,
      });
      if (!startRes.ok) throw new Error('Erreur au démarrage');
      const { job_id } = await startRes.json();

      const interval = setInterval(async () => {
        const statusRes = await fetch(`${API_BASE}/optimize/status/${job_id}`);
        if (!statusRes.ok) {
          clearInterval(interval);
          setRunning(false);
          alert('Erreur de statut');
          return;
        }
        const status = await statusRes.json();

        if (status.gap != null) {
          const p = Math.max(1, Math.min(99, Math.round(100 - status.gap)));
          setProgress(p);
        }

        if (status.status === 'done') {
          clearInterval(interval);
          setProgress(100);
          const result = status.result;
          const runsForThisImport = runs.filter(r => r.importId === imp.id);
          const runType: 'base' | 'personnalise' = runsForThisImport.length === 0 ? 'base' : 'personnalise';
          const label = runType === 'base' ? 'Cas de base' : `Variante #${runsForThisImport.length}`;

          const newRun = buildRunFromResult(result, imp.id, runType, label, simParams);
          setRuns(prev => [...prev, newRun]);
          setActiveRunId(newRun.id);
          setRunning(false);
          setPage('dashboard');
        }
        if (status.status === 'error') {
          clearInterval(interval);
          setRunning(false);
          alert('Erreur: ' + status.error);
        }
      }, 1500);
    } catch (err) {
      console.error(err);
      setRunning(false);
      alert('Erreur: ' + (err as Error).message);
    }
  };

  // ── Fonction pivotStock corrigée ─────────────────────────────────────
  const pivotStock = (records: any[], keyField: string, allKeys: string[] = []) => {
    const weeks = [0, 1, 2, 3, 4];
    const pivotMap: Record<number, Record<string, number>> = {};
    weeks.forEach(t => {
      pivotMap[t] = {};
      allKeys.forEach(k => { pivotMap[t][k] = 0; });
    });

    records.forEach((r: any) => {
      const t = r.semaine;
      if (t === undefined) return;
      const key = r[keyField];
      if (key && pivotMap[t][key] !== undefined) {
        pivotMap[t][key] += r.stock || 0;
      }
    });

    return weeks.map(t => {
      const row: any = { t: `t=${t}` };
      allKeys.forEach(k => {
        row[k] = pivotMap[t][k] || 0;
      });
      return row;
    });
  };

  const buildRunFromResult = (result: any, importId: string, runType: 'base' | 'personnalise', label: string, params: SimParams): RunResult => {
    const totalHonore = result.commandes_acceptees_detail.reduce((acc: number, r: any) => acc + r.tonnage, 0);
    const totalRefuse = result.commandes_refusees.reduce((acc: number, r: any) => acc + r.tonnage, 0);
    const totalDemande = totalHonore + totalRefuse;
    const tauxService = totalDemande > 0 ? (totalHonore / totalDemande) * 100 : 0;

    const utilVals = result.utilisation_lignes.map((u: any) => u.taux);
    const utilisationMoyenne = utilVals.length > 0
      ? Math.round((utilVals.reduce((a: number, b: number) => a + b, 0) / utilVals.length) * 10) / 10
      : 0;

    const machinesSet = new Set(result.utilisation_lignes.map((u: any) => u.machine));
    const lignesArray = Array.from(machinesSet).map((mach) => {
      const entries = result.utilisation_lignes.filter((u: any) => u.machine === mach);
      const s = [];
      for (let t = 1; t <= 4; t++) {
        const found = entries.find((u: any) => u.semaine === t);
        s.push({
          t: found ? found.tonnage : 0,
          p: found ? found.taux : 0,
          capacite: found ? found.capacite : 0,
        });
      }
      const moy = s.reduce((acc, cur) => acc + cur.p, 0) / s.length;
      return { ligne: mach, cap: 0, s, moy };
    });

    const weeks = [0, 1, 2, 3, 4];
    const stockPkTotal = weeks.map(t => ({
      t: `t=${t}`,
      PK: result.stocks.pk.filter((s: any) => s.semaine === t).reduce((a: number, s: any) => a + s.stock, 0),
    }));

    const stockPkByGrade = pivotStock(result.stocks.pk, 'grade', ['DC01','DD13','DX51','DX52','S320']);
    const stockFiniByFamille = pivotStock(result.stocks.fini, 'famille', ['CRC','HDG','PPGI','BACR']);
    const stockInterByPoint = pivotStock(result.stocks.inter, 'point', ['FH-CRMA','FH-CRMB','BAF-out','SKP-out']);
    const consoHrcByGrade = pivotStock(result.conso_hrc_semaine || [], 'grade', ['DC01','DD13','DX51','DX52','S320']);

    const commandesDetail: Commande[] = [];
    result.commandes_acceptees_detail.forEach((cmd: any) => {
      let statut = "Honorée";
      const semProd = cmd.semaine_prod;
      const semLiv = cmd.semaine_liv;
      if (semProd !== null && semProd !== undefined) {
        if (semProd < semLiv) statut = "En avance";
        else if (semProd === semLiv) statut = "Honorée";
        else statut = "En retard";
      }
      commandesDetail.push({
        id: cmd.id,
        client: cmd.client || "—",
        famille: cmd.famille,
        grade: cmd.grade || "",
        ep: cmd.epaisseur || 0,
        larg: cmd.largeur || 0,
        ton: cmd.tonnage,
        prio: cmd.priorite || "Normale",
        semLiv: cmd.semaine_liv || 0,
        statut: statut,
        semProd: semProd !== null && semProd !== undefined ? semProd : null,
        retard: semProd !== null && semProd > semLiv ? semProd - semLiv : 0,
        margeMad: cmd.marge_mad ?? 0,
        margeUnitaireMad: cmd.marge_unitaire_mad ?? 0,
        prixVente: cmd.prix_vente ?? 0,
      });
    });
    result.commandes_refusees.forEach((cmd: any) => {
      commandesDetail.push({
        id: cmd.id,
        client: cmd.client || "—",
        famille: cmd.famille,
        grade: cmd.grade || "",
        ep: 0,
        larg: 0,
        ton: cmd.tonnage,
        prio: cmd.priorite || "Normale",
        semLiv: cmd.semaine_liv || 0,
        statut: "Refusée",
        semProd: null,
        retard: 0,
        margeMad: 0,
        margeUnitaireMad: 0,
        prixVente: cmd.prix ?? 0,
      });
    });

    const refusees = result.commandes_refusees.map((r: any) => ({
      id: r.id,
      client: r.client || "—",
      produit: `${r.famille} ${r.grade} ${r.tonnage}T`,
      tonnage: r.tonnage,
      raison: r.raison_principale || r.raison || (r.priorite ? `Priorité ${r.priorite}` : 'Capacité'),
      contraintes_bloquantes: r.contraintes_bloquantes || [],
    }));

    const bnbTree = result.bnb_tree ? {
      nodes: result.bnb_tree.nodes.map((n: any) => ({
        nodeId: n.node_id,
        nodesLeft: n.nodes_left,
        bestBound: n.best_bound,
        bestInt: n.best_int,
        gap: n.gap,
      })),
      totalLeaves: result.bnb_tree.total_leaves,
      bestBoundEvolution: result.bnb_tree.best_bound_evolution,
    } : null;

    return {
      id: Date.now(),
      importId,
      runType,
      label,
      executedAt: new Date().toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }),
      duree: result.temps_execution + ' sec',
      saved: false,
      paramsUsed: { 
        gap: params.gap, 
        campagneActive: params.campagneActive,
        overrides: params.overrides,
      },
      marge: result.marge / 1_000_000,
      tauxService: tauxService,
      commandes: `${result.commandes_acceptees.length}/${result.commandes_acceptees.length + result.commandes_refusees.length}`,
      weekly: result.production_par_semaine.map((s: any) => ({
        sem: `Sem. ${s.semaine}`,
        CRC: s.CRC,
        HDG: s.HDG,
        PPGI: s.PPGI,
        BACR: s.BACR,
      })),
      margeFamily: result.marge_par_famille.map((f: any) => ({
        name: f.name,
        value: f.value / 1_000_000,
        pct: f.pct,
      })),
      statutData: result.statut_commandes.map((s: any) => ({
        name: s.name,
        value: s.value,
        pct: s.pct,
        color: s.name.includes('échéance') ? C.green : s.name.includes('avance') ? C.blue : s.name.includes('retard') ? C.orange : C.red,
      })),
      lignes: lignesArray,
      contraintes: result.contraintes || [],
      refusees: refusees,
      stockChartData: result.stockChartData || [],
      commandesDetail: commandesDetail,
      exportFile: result.export_file ?? null,
      commandesRefuseesCount: result.commandes_refusees.length,
      commandesRefuseesTonnage: result.commandes_refusees.reduce((a: number, r: any) => a + r.tonnage, 0),
      utilisationMoyenne: utilisationMoyenne,
      planProduction: result.plan_production || [],
      stockPkTotal,
      stockPkByGrade,
      stockFiniByFamille,
      stockInterByPoint,
      consoHrcByGrade,
      bnbTree,
    };
  };

  const handleExport = () => {
    if (activeRun?.exportFile) {
      const link = document.createElement('a');
      link.href = `${API_BASE}/download/${activeRun.exportFile}`;
      link.download = activeRun.exportFile;
      link.click();
    } else {
      alert('Aucun fichier exporté disponible pour ce run.');
    }
  };

  const toggleCompare = (id: number) => {
    setCompareIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id].slice(-8)
    );
  };

  const pageLabel = NAV.find(n => n.id === page)?.label ?? "";

  const renderPage = () => {
    if (isLoadingRuns) {
      return <div className="flex items-center justify-center h-64" style={{ color: C.muted }}>Chargement des données...</div>;
    }

    if (!activeRun && page !== 'scenarios' && page !== 'historique' && page !== 'comparaison') {
      return (
        <div className="flex flex-col items-center justify-center h-64" style={{ color: C.muted }}>
          <AlertCircle size={32} className="mb-2" />
          <p className="text-lg font-semibold">Aucune simulation chargée</p>
          <p className="text-sm">Importez un fichier Excel et lancez une simulation depuis la page Scénarios.</p>
          <button onClick={() => setPage('scenarios')} className="mt-4 px-4 py-2 rounded text-white text-sm" style={{ backgroundColor: C.blue }}>
            Aller aux scénarios
          </button>
        </div>
      );
    }

    switch(page) {
      case "dashboard":
        return <DashboardPage data={activeRun!} onConfigure={() => setPage('scenarios')} onSave={() => activeRun && handleSaveRun(activeRun.id)} />;
      case "commandes":
        return <CommandesPage data={activeRun!} />;
      case "plan":
        return <PlanDeMarchePage data={activeRun!} />;
      case "plan_production":
        return <PlanProductionPage data={activeRun} />;
      case "stocks":
        return <StocksPage data={activeRun} />;
      case "resultats":
        return <ResultatsPage data={activeRun!} onExport={handleExport} />;
      case "scenarios":
        return (
          <ScenariosPage
            imports={imports}
            activeImportId={activeImportId}
            setActiveImportId={setActiveImportId}
            simParams={simParams}
            setSimParams={handleSetSimParams}
            onLaunch={handleLaunch}
            running={running}
            progress={progress}
            uploadedFileUrl={uploadedFileUrl}
            uploadedFileName={uploadedFileName}
            onUpload={handleUpload}
            overrides={simParams.overrides}
            setOverrides={handleSetOverrides}
            loadingParams={loadingParams}
          />
        );
      case "historique":
        return (
          <HistoriquePage
            imports={imports}
            runs={runs}
            onSelectRun={(id) => { setActiveRunId(id); setPage('dashboard'); }}
            onSaveRun={handleSaveRun}
            onDeleteRun={handleDeleteRun}
            compareIds={compareIds}
            toggleCompare={toggleCompare}
            onCompare={() => setPage('comparaison')}
          />
        );
      case "comparaison":
        return <ComparateurPage runs={runs} compareIds={compareIds} />;
      default:
        return null;
    }
  };

  return (
    <div className="h-screen flex flex-col overflow-hidden" style={{ fontFamily: "'Inter', sans-serif" }}>

      <header className="flex items-center gap-4 px-5 py-2.5 flex-shrink-0" style={{ backgroundColor: C.navy }}>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">

            <span className="text-white font-bold text-sm tracking-widest">MAGHREB STEEL</span>
          </div>
          <div className="w-px h-5" style={{ backgroundColor: "rgba(255,255,255,0.2)" }} />
          <div>
            <div className="text-white text-xs font-semibold tracking-wide">SIMULATEUR CAPACITÉ-COMMANDE</div>
            <div className="text-xs" style={{ color: "rgba(255,255,255,0.5)" }}>Planification optimale sur 4 semaines</div>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          {[Settings, HelpCircle].map((Icon, i) => (
            <button key={i} className="w-7 h-7 rounded flex items-center justify-center transition-colors" style={{ backgroundColor: "rgba(255,255,255,0.08)" }}
              onMouseOver={e => (e.currentTarget.style.backgroundColor="rgba(255,255,255,0.16)")}
              onMouseOut={e  => (e.currentTarget.style.backgroundColor="rgba(255,255,255,0.08)")}>
              <Icon size={13} style={{ color: "rgba(255,255,255,0.65)" }} />
            </button>
          ))}
          <button className="w-7 h-7 rounded-full flex items-center justify-center ml-1" style={{ backgroundColor: "rgba(255,255,255,0.18)" }}>
            <User size={13} className="text-white" />
          </button>
        </div>
      </header>

      <nav className="flex items-center bg-white border-b border-gray-200 px-3 flex-shrink-0" style={{ minHeight: 42 }}>
        <div className="flex items-center gap-0.5 flex-1 overflow-x-auto">
          {NAV.map(({ id, label, Icon }) => (
            <button key={id} onClick={() => setPage(id)}
              className="flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium transition-all border-b-2 -mb-px whitespace-nowrap flex-shrink-0"
              style={{
                borderBottomColor: page===id ? C.blue : "transparent",
                color: page===id ? C.blue : C.muted,
              }}>
              <Icon size={12} />
              {label}
            </button>
          ))}
        </div>
      </nav>

      <div className="flex flex-1 overflow-hidden">

        {page !== "scenarios" && page !== "historique" && page !== "comparaison" && (
          <div className="flex flex-shrink-0" style={{ width: sidebarWidth }}>
            <aside className="w-full border-r border-gray-200 bg-white flex flex-col overflow-y-auto text-xs">
              <div className="p-3 border-b border-gray-100">
                <div className="font-bold uppercase tracking-wider mb-3" style={{ color: C.muted }}>
                  Run en consultation
                </div>
                <div className="space-y-3">
                  <div>
                    <label className="block mb-1 font-medium text-xs" style={{ color: C.muted }}>
                      Run actif
                    </label>
                    <select
                      className="w-full border border-gray-200 rounded px-2 py-1.5 bg-white text-xs"
                      value={activeRunId ?? ''}
                      onChange={e => setActiveRunId(Number(e.target.value))}
                    >
                      <option value="">-- Aucun --</option>
                      {runs.map(r => (
                        <option key={r.id} value={r.id}>{r.label} — {r.executedAt}</option>
                      ))}
                    </select>
                  </div>
                  {activeRun && (
                    <div className="text-xs space-y-1.5" style={{ color: C.muted }}>
                      <div className="flex justify-between">
                        <span>Type</span>
                        <Badge
                          label={activeRun.runType === 'base' ? 'Base' : 'Personnalisé'}
                          bg={activeRun.runType === 'base' ? '#ECFDF5' : '#EFF6FF'}
                          text={activeRun.runType === 'base' ? C.green : C.blue}
                        />
                      </div>
                      <div className="flex justify-between">
                        <span>Campagne</span>
                        <strong style={{ color: C.navy }}>
                          {activeRun.paramsUsed.campagneActive ? 'Oui' : 'Non'}
                        </strong>
                      </div>
                      <div className="flex justify-between">
                        <span>Gap utilisé</span>
                        <strong style={{ color: C.navy }}>{activeRun.paramsUsed.gap.toFixed(3)}%</strong>
                      </div>
                      {(() => {
                        const o = activeRun?.paramsUsed.overrides;
                        if (!o) return null;
                        const n = [
                          o.prix_zinc, o.prix_peinture, o.conso_zinc_hdg, o.conso_zinc_ppgi,
                          o.conso_peinture, o.pen_haute, o.pen_normale, o.pen_basse,
                          o.cout_stock_inter, o.cout_stock_fini, o.prix_chute,
                        ].filter(v => v !== "").length
                        + Object.values(o.dispo_hrc).filter(v => v !== "").length
                        + Object.values(o.arrets).filter(v => v !== "").length;
                        if (n === 0) return null;
                        return (
                          <div className="flex justify-between">
                            <span>Surcharges</span>
                            <Badge label={`${n} actives`} bg="#FFF7ED" text={C.orange} />
                          </div>
                        );
                      })()}
                      <div className="flex justify-between">
                        <span>Fichier</span>
                        <strong style={{ color: C.navy }}>
                          {imports.find(i => i.id === activeRun.importId)?.fileName ?? '—'}
                        </strong>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div className="p-3 border-b border-gray-100">
                <button
                  onClick={() => setPage("scenarios")}
                  onMouseOver={() => setIsHoverConfig(true)}
                  onMouseOut={() => setIsHoverConfig(false)}
                  className="w-full py-2.5 rounded font-bold flex items-center justify-center gap-2 text-white transition-shadow"
                  style={{
                    backgroundColor: isHoverConfig ? '#E67E22' : C.orange,
                    boxShadow: isHoverConfig ? '0 4px 6px rgba(0,0,0,0.1)' : 'none'
                  }}
                >
                  <Settings size={12} /> Configurer un scénario
                </button>
              </div>

              <div className="p-3 border-b border-gray-100">
                <div style={{ color: C.muted }} className="mb-1 text-xs">Dernière exécution</div>
                <div className="font-mono text-xs text-gray-600">{activeRun?.executedAt ?? '—'}</div>
                <div className="flex items-center gap-2 mt-1.5">
                  <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: C.green }} />
                  <span className="text-xs font-medium" style={{ color: C.green }}>Terminée</span>
                  <span style={{ color: C.muted }} className="text-xs">{activeRun?.duree ?? '—'}</span>
                </div>
              </div>


            </aside>
            <div
              className="cursor-col-resize flex-shrink-0"
              style={{ width: 4, backgroundColor: 'transparent' }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#E2E8F0')}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
              onMouseDown={(e) => {
                e.preventDefault();
                const startX = e.clientX;
                const startWidth = sidebarWidth;
                const onMouseMove = (ev: MouseEvent) => {
                  const newWidth = Math.min(420, Math.max(180, startWidth + (ev.clientX - startX)));
                  setSidebarWidth(newWidth);
                };
                const onMouseUp = () => {
                  window.removeEventListener('mousemove', onMouseMove);
                  window.removeEventListener('mouseup', onMouseUp);
                };
                window.addEventListener('mousemove', onMouseMove);
                window.addEventListener('mouseup', onMouseUp);
              }}
            />
          </div>
        )}

        <main className="flex-1 overflow-auto p-4" style={{ backgroundColor: C.gray }}>
          <div className="flex items-start justify-between mb-4">
            <div>
              <h1 className="text-base font-bold" style={{ color: C.navy }}>{pageLabel}</h1>
              <p className="text-xs mt-0.5" style={{ color: C.muted }}>
                Horizon : 05/05/2026 – 01/06/2026 · 4 semaines
                {activeRun && ` · ${activeRun.label}`}
              </p>
            </div>
          </div>
          {renderPage()}
        </main>
      </div>
    </div>
  );
}