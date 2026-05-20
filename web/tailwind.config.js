/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "InterVariable",
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "sans-serif",
        ],
      },
      colors: {
        brand: {
          navy: "#1B2A4A",
          "navy-light": "#243556",
          "navy-dark": "#111D35",
          orange: "#D04A02",
          "orange-light": "#E8660F",
          "orange-dark": "#B03D00",
          gold: "#E88D2A",
          "gold-light": "#F5A94D",
          rose: "#D93954",
          tan: "#F7F4F0",
          cream: "#FBF9F7",
        },
      },
    },
  },
  plugins: [],
};
