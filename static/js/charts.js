/* KrishiMitra — Chart.js helper wrappers used by dashboard.html,
   economics.html and admin_dashboard.html. Keeps chart configuration
   (colors, fonts) consistent with the rest of the design system. */

(function () {
    const PALETTE = ["#14532D", "#C99A2E", "#6B4423", "#2C5C77", "#B3402A", "#4B564C"];

    function baseFont() {
        return { family: "Inter, sans-serif", size: 12 };
    }

    function createLineChart(canvasId, labels, data, label) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        return new Chart(ctx, {
            type: "line",
            data: {
                labels,
                datasets: [{
                    label, data,
                    borderColor: "#14532D",
                    backgroundColor: "rgba(20, 83, 45, 0.12)",
                    tension: 0.35, fill: true, pointRadius: 3,
                }],
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { font: baseFont() }, grid: { display: false } },
                    y: { ticks: { font: baseFont() }, grid: { color: "#EEF1E9" } },
                },
            },
        });
    }

    function createDoughnutChart(canvasId, labels, data) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        return new Chart(ctx, {
            type: "doughnut",
            data: { labels, datasets: [{ data, backgroundColor: PALETTE, borderWidth: 0 }] },
            options: {
                responsive: true,
                plugins: { legend: { position: "bottom", labels: { font: baseFont(), boxWidth: 12 } } },
                cutout: "62%",
            },
        });
    }

    function createBarChart(canvasId, labels, data, label) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        return new Chart(ctx, {
            type: "bar",
            data: { labels, datasets: [{ label, data, backgroundColor: "#14532D", borderRadius: 6, maxBarThickness: 36 }] },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { font: baseFont() }, grid: { display: false } },
                    y: { ticks: { font: baseFont() }, grid: { color: "#EEF1E9" } },
                },
            },
        });
    }

    window.KrishiCharts = { createLineChart, createDoughnutChart, createBarChart };
})();
