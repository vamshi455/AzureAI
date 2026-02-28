import { useQuery } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { TrendingUp, TrendingDown, DollarSign, Package, Factory, ShoppingCart } from "lucide-react";
import { analyticsApi, type KPIData, type DemandForecast } from "../services/api";

// --- KPI Card Component ---
interface KPICardProps {
  title: string;
  value: string;
  change: number;
  icon: React.ReactNode;
  prefix?: string;
}

function KPICard({ title, value, change, icon, prefix = "" }: KPICardProps) {
  const isPositive = change >= 0;
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm font-medium text-gray-500">{title}</span>
        <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center">
          {icon}
        </div>
      </div>
      <div className="text-2xl font-bold text-gray-900">
        {prefix}{value}
      </div>
      <div className={`flex items-center gap-1 mt-2 text-sm ${isPositive ? "text-green-600" : "text-red-600"}`}>
        {isPositive ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
        <span>{isPositive ? "+" : ""}{change.toFixed(1)}% vs last period</span>
      </div>
    </div>
  );
}

// --- Chart Color Palette ---
const COLORS = ["#2563eb", "#7c3aed", "#db2777", "#ea580c", "#16a34a", "#ca8a04"];

// --- Fallback data generators for demo ---
function generateSalesData() {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return months.map((month) => ({
    month,
    revenue: Math.floor(Math.random() * 500000 + 800000),
    orders: Math.floor(Math.random() * 2000 + 3000),
    avgOrderValue: Math.floor(Math.random() * 100 + 250),
  }));
}

function generateForecastData(): DemandForecast[] {
  const weeks: DemandForecast[] = [];
  for (let i = 1; i <= 12; i++) {
    const actual = i <= 6 ? Math.floor(Math.random() * 5000 + 15000) : undefined;
    weeks.push({
      period: `W${i}`,
      actual: actual ?? 0,
      predicted: Math.floor(Math.random() * 5000 + 14000),
      lower_bound: Math.floor(Math.random() * 3000 + 11000),
      upper_bound: Math.floor(Math.random() * 3000 + 18000),
    });
  }
  return weeks;
}

function generateManufacturingData() {
  const lines = ["Line A", "Line B", "Line C", "Line D"];
  return lines.map((line) => ({
    line,
    efficiency: Math.floor(Math.random() * 15 + 82),
    defectRate: +(Math.random() * 3 + 0.5).toFixed(1),
    throughput: Math.floor(Math.random() * 500 + 800),
    downtime: Math.floor(Math.random() * 30 + 5),
  }));
}

function generateProductMixData() {
  return [
    { name: "Electronics", value: 35 },
    { name: "Industrial Parts", value: 25 },
    { name: "Consumer Goods", value: 20 },
    { name: "Raw Materials", value: 12 },
    { name: "Services", value: 8 },
  ];
}

function generatePipelineStatusData() {
  return [
    { name: "Sales Ingestion", status: "success", records: 245891, duration: 12 },
    { name: "Manufacturing Telemetry", status: "running", records: 512340, duration: 45 },
    { name: "Demand Forecast", status: "success", records: 18420, duration: 28 },
    { name: "Inventory Sync", status: "success", records: 8930, duration: 8 },
    { name: "Customer 360", status: "failed", records: 0, duration: 0 },
    { name: "Quality Metrics", status: "success", records: 34210, duration: 15 },
  ];
}

// --- Dashboard Page ---
export default function Dashboard() {
  // Fetch KPIs from API (with fallback)
  const { data: kpis } = useQuery<KPIData>({
    queryKey: ["kpis"],
    queryFn: analyticsApi.getKPIs,
    placeholderData: {
      totalRevenue: 12450000,
      revenueChange: 8.3,
      totalOrders: 34521,
      ordersChange: 5.7,
      productionOutput: 892400,
      productionChange: -2.1,
      avgOrderValue: 361,
      avgOrderValueChange: 3.2,
    },
  });

  // Fetch demand forecast
  const { data: forecast } = useQuery<DemandForecast[]>({
    queryKey: ["demand-forecast"],
    queryFn: analyticsApi.getDemandForecast,
    placeholderData: generateForecastData(),
  });

  const salesData = generateSalesData();
  const manufacturingData = generateManufacturingData();
  const productMix = generateProductMixData();
  const pipelineStatus = generatePipelineStatusData();

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Analytics Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">
          Manufacturing & Sales intelligence overview
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <KPICard
          title="Total Revenue"
          value={(kpis?.totalRevenue ?? 0).toLocaleString()}
          change={kpis?.revenueChange ?? 0}
          icon={<DollarSign className="w-5 h-5 text-blue-600" />}
          prefix="$"
        />
        <KPICard
          title="Total Orders"
          value={(kpis?.totalOrders ?? 0).toLocaleString()}
          change={kpis?.ordersChange ?? 0}
          icon={<ShoppingCart className="w-5 h-5 text-blue-600" />}
        />
        <KPICard
          title="Production Output"
          value={(kpis?.productionOutput ?? 0).toLocaleString()}
          change={kpis?.productionChange ?? 0}
          icon={<Factory className="w-5 h-5 text-blue-600" />}
        />
        <KPICard
          title="Avg Order Value"
          value={(kpis?.avgOrderValue ?? 0).toLocaleString()}
          change={kpis?.avgOrderValueChange ?? 0}
          icon={<Package className="w-5 h-5 text-blue-600" />}
          prefix="$"
        />
      </div>

      {/* Row: Revenue Trend + Product Mix */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Revenue & Orders Trend</h3>
          <ResponsiveContainer width="100%" height={320}>
            <AreaChart data={salesData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="month" tick={{ fontSize: 12 }} />
              <YAxis yAxisId="left" tick={{ fontSize: 12 }} tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12 }} />
              <Tooltip formatter={(value: number, name: string) => name === "revenue" ? [`$${value.toLocaleString()}`, "Revenue"] : [value.toLocaleString(), "Orders"]} />
              <Legend />
              <Area yAxisId="left" type="monotone" dataKey="revenue" stroke="#2563eb" fill="#2563eb20" name="Revenue" />
              <Line yAxisId="right" type="monotone" dataKey="orders" stroke="#7c3aed" strokeWidth={2} dot={false} name="Orders" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Product Mix</h3>
          <ResponsiveContainer width="100%" height={320}>
            <PieChart>
              <Pie data={productMix} cx="50%" cy="50%" innerRadius={60} outerRadius={100} paddingAngle={4} dataKey="value" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                {productMix.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Row: Demand Forecast */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-8">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Demand Forecast (12-Week)</h3>
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart data={forecast}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="period" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k`} />
            <Tooltip />
            <Legend />
            <Area type="monotone" dataKey="upper_bound" stroke="none" fill="#2563eb10" name="Upper Bound" />
            <Area type="monotone" dataKey="lower_bound" stroke="none" fill="#ffffff" name="Lower Bound" />
            <Line type="monotone" dataKey="actual" stroke="#16a34a" strokeWidth={2} name="Actual" dot />
            <Line type="monotone" dataKey="predicted" stroke="#2563eb" strokeWidth={2} strokeDasharray="5 5" name="Predicted" dot />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Row: Manufacturing Metrics + Pipeline Status */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Manufacturing Metrics */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Manufacturing Line Performance</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={manufacturingData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 12 }} />
              <YAxis type="category" dataKey="line" tick={{ fontSize: 12 }} width={60} />
              <Tooltip />
              <Legend />
              <Bar dataKey="efficiency" fill="#2563eb" name="Efficiency (%)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>

          {/* Manufacturing detail table */}
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-gray-500">Line</th>
                  <th className="px-3 py-2 text-right font-medium text-gray-500">Throughput</th>
                  <th className="px-3 py-2 text-right font-medium text-gray-500">Defect Rate</th>
                  <th className="px-3 py-2 text-right font-medium text-gray-500">Downtime (min)</th>
                </tr>
              </thead>
              <tbody>
                {manufacturingData.map((row) => (
                  <tr key={row.line} className="border-t border-gray-100">
                    <td className="px-3 py-2 font-medium">{row.line}</td>
                    <td className="px-3 py-2 text-right">{row.throughput.toLocaleString()}</td>
                    <td className={`px-3 py-2 text-right ${row.defectRate > 2 ? "text-red-600 font-medium" : "text-green-600"}`}>
                      {row.defectRate}%
                    </td>
                    <td className="px-3 py-2 text-right">{row.downtime}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Pipeline Status */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Data Pipeline Status</h3>
          <div className="space-y-3">
            {pipelineStatus.map((pipeline) => {
              const statusConfig = {
                success: { bg: "bg-green-50", text: "text-green-700", border: "border-green-200", label: "Completed" },
                running: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-200", label: "Running" },
                failed: { bg: "bg-red-50", text: "text-red-700", border: "border-red-200", label: "Failed" },
              }[pipeline.status] || { bg: "bg-gray-50", text: "text-gray-700", border: "border-gray-200", label: "Unknown" };

              return (
                <div key={pipeline.name} className={`flex items-center justify-between p-4 rounded-lg border ${statusConfig.bg} ${statusConfig.border}`}>
                  <div>
                    <div className="font-medium text-gray-900">{pipeline.name}</div>
                    <div className="text-xs text-gray-500 mt-1">
                      {pipeline.records > 0 ? `${pipeline.records.toLocaleString()} records` : "No data"}
                      {pipeline.duration > 0 ? ` | ${pipeline.duration} min` : ""}
                    </div>
                  </div>
                  <span className={`px-3 py-1 rounded-full text-xs font-medium ${statusConfig.text} ${statusConfig.bg}`}>
                    {statusConfig.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
