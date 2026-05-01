export default {
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        studio: {
          black: "#0A0A0A",
          charcoal: "#111113",
          panel: "rgba(255,255,255,0.045)",
          panelBorder: "rgba(255,255,255,0.10)",
          muted: "#8A8F98",
          text: "#F4F7FA",
          cyan: "#22D3EE",
          teal: "#2DD4BF",
        },
      },

      fontFamily: {
        sans: ["Inter", "Geist", "Geist Sans", "ui-sans-serif", "system-ui"],
      },

      boxShadow: {
        "cyan-glow": "0 0 24px rgba(34, 211, 238, 0.28)",
        "cyan-glow-lg": "0 0 40px rgba(34, 211, 238, 0.38)",
        "teal-glow": "0 0 28px rgba(45, 212, 191, 0.25)",
        "panel-soft": "0 20px 60px rgba(0, 0, 0, 0.45)",
        "inset-depth":
          "inset 0 1px 1px rgba(255,255,255,0.04), inset 0 -20px 40px rgba(0,0,0,0.35)",
      },

      backgroundImage: {
        "panel-gradient":
          "linear-gradient(180deg, rgba(255,255,255,0.075) 0%, rgba(255,255,255,0.035) 100%)",
        "workspace-radial":
          "radial-gradient(circle at top center, rgba(34,211,238,0.10), transparent 36%), linear-gradient(180deg, #0A0A0A 0%, #050505 100%)",
        "timeline-gradient":
          "linear-gradient(180deg, rgba(255,255,255,0.035), rgba(0,0,0,0.35))",
      },
    },
  },
};
