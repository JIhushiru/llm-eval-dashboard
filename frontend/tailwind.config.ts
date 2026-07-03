import type { Config } from "tailwindcss";

// Visual system tokens from SPEC section 10. Colors resolve to CSS variables
// (RGB channels, so Tailwind opacity modifiers like `bg-good/10` still work)
// defined in globals.css and flipped per theme via the [data-theme] attribute.
const rgbVar = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

const config: Config = {
  darkMode: ["selector", '[data-theme="dark"]'],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        page: rgbVar("page"),
        surface: rgbVar("surface"),
        hairline: "var(--hairline)",
        ink: rgbVar("ink"),
        ink2: rgbVar("ink2"),
        ink3: rgbVar("ink3"),
        accent: rgbVar("accent"),
        good: rgbVar("good"),
        warning: rgbVar("warning"),
        serious: rgbVar("serious"),
        critical: rgbVar("critical"),
        grid: rgbVar("grid"),
        axis: rgbVar("axis"),
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
