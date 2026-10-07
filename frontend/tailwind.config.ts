import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Exact tokens from static/app.css :root
        bg: "#fffcf7", // --paper
        surface: "#fffcf7",
        border: "rgba(23, 48, 44, 0.14)", // --line
        violet: { DEFAULT: "#0f6e62", soft: "rgba(15, 110, 98, 0.14)" }, // --signal
        emerald: { DEFAULT: "#0f6e62", soft: "rgba(15, 110, 98, 0.14)" },
        amber: { DEFAULT: "#9a5b2e", soft: "rgba(154, 91, 46, 0.14)" },
        rose: { DEFAULT: "#9c3218", soft: "rgba(156, 50, 24, 0.1)" }, // --warn
        muted: "#4a625c", // --muted
        ink: "#17302c", // --ink (primary text)
        "signal-ink": "#f4faf8", // --signal-ink
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
