"use client";

/**
 * Background — soft pastel mesh blobs only.
 * NO floating particles, NO canvas, NO lines.
 * Just large, creamy, slowly drifting gradient blobs
 * behind a subtle grain texture overlay.
 */
export default function ParticlesBackground() {
  return (
    <div style={{
      position: "fixed",
      top: 0, left: 0,
      width: "100vw", height: "100vh",
      zIndex: -1,
      overflow: "hidden",
      background: "#faf7f5",
    }}>
      {/* Soft pastel mesh blobs */}
      <div className="mesh-blob blob-1"></div>
      <div className="mesh-blob blob-2"></div>
      <div className="mesh-blob blob-3"></div>
      <div className="mesh-blob blob-4"></div>
      <div className="mesh-blob blob-5"></div>

      {/* Grain texture overlay for matte feel */}
      <div className="grain-overlay"></div>
    </div>
  );
}
