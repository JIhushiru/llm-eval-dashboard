import type { Config } from "tailwindcss";

// Visual system tokens from SPEC section 10 (light mode).
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        page: "#f9f9f7",
        surface: "#fcfcfb",
        hairline: "rgba(11,11,11,0.10)",
        ink: "#0b0b0b",
        ink2: "#52514e",
        ink3: "#898781",
        accent: "#2a78d6",
        good: "#0ca30c",
        warning: "#fab219",
        serious: "#ec835a",
        critical: "#d03b3b",
        grid: "#e1e0d9",
        axis: "#c3c2b7",
      },
      fontFamily: {
        sans: [
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
