/* KrishiMitra — generic form helpers (clear buttons, live counters) */

(function () {
    document.addEventListener("DOMContentLoaded", () => {
        // Any button with data-clear-form="formId" resets that form
        document.querySelectorAll("[data-clear-form]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const form = document.getElementById(btn.getAttribute("data-clear-form"));
                if (form) form.reset();
            });
        });

        // Range inputs: mirror the live value into an adjacent output tag
        document.querySelectorAll("input[type=range][data-output]").forEach((range) => {
            const out = document.getElementById(range.getAttribute("data-output"));
            const sync = () => { if (out) out.textContent = range.value; };
            range.addEventListener("input", sync);
            sync();
        });
    });
})();
