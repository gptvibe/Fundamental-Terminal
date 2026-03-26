export default function CompanyRouteLoading() {
  return (
    <div className="company-workspace-stack" style={{ display: "grid", gap: 16 }}>
      <div
        className="panel"
        style={{
          minHeight: 88,
          background: "linear-gradient(90deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.03) 100%)",
          backgroundSize: "200% 100%",
          animation: "company-load-shimmer 1.2s ease-in-out infinite",
        }}
      />
      <div style={{ display: "grid", gap: 12 }}>
        <div
          className="panel"
          style={{
            minHeight: 160,
            background: "linear-gradient(90deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.03) 100%)",
            backgroundSize: "200% 100%",
            animation: "company-load-shimmer 1.2s ease-in-out infinite",
          }}
        />
        <div
          className="panel"
          style={{
            minHeight: 260,
            background: "linear-gradient(90deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.03) 100%)",
            backgroundSize: "200% 100%",
            animation: "company-load-shimmer 1.2s ease-in-out infinite",
          }}
        />
      </div>
    </div>
  );
}
