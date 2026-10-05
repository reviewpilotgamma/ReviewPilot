import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: "#0b0f19",
        surface: "#111827",
        border: "#1f2937",
        violet: { DEFAULT: "#8b5cf6", soft: "rgba(139,92,246,0.15)" },
        emerald: { DEFAULT: "#10b981", soft: "rgba(16,185,129,0.15)" },
        amber: { DEFAULT: "#f59e0b", soft: "rgba(245,158,11,0.15)" },
        rose: { DEFAULT: "#f43f5e", soft: "rgba(244,63,94,0.15)" },
        muted: "#9ca3af",
        text: "#e5e7eb",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      keyframes: {
        "slide-in": { from: { transform: "translateX(100%)" }, to: { transform: "translateX(0)" } },
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
      },
      animation: {
        "slide-in": "slide-in 200ms ease-out",
        "fade-in": "fade-in 150ms ease-out",
      },
    },
  },
  plugins: [],
} satisfies Config;
