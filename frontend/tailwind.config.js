/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx,js,jsx}"],
  theme: {
    extend: {
      colors: {
        favorable: "#16a34a",   // green-600
        sensitive: "#ca8a04",   // yellow-600
        bad: "#dc2626",         // red-600
        target: "#bf5700",      // Texas burnt orange
      },
    },
  },
  plugins: [],
};
