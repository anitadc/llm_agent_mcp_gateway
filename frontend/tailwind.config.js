/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eff6ff",
          100: "#dbeafe",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
        },
        status: {
          success: "#16a34a",
          error: "#dc2626",
          blocked: "#d97706",
          rate_limited: "#9333ea",
        },
      },
    },
  },
  plugins: [],
};
