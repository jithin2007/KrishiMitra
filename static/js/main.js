/* KrishiMitra — shared front-end behaviour */

(function () {
    function showToast(message, category) {
        const stack = document.getElementById("toast-stack");
        if (!stack) return;
        const el = document.createElement("div");
        const cls = { danger: "toast-danger", success: "toast-success", warning: "toast-warning", info: "" }[category] || "";
        el.className = "toast " + cls;
        el.textContent = message;
        stack.appendChild(el);
        setTimeout(() => {
            el.style.transition = "opacity 0.3s ease";
            el.style.opacity = "0";
            setTimeout(() => el.remove(), 300);
        }, 4200);
    }

    document.addEventListener("DOMContentLoaded", () => {
        const flashData = document.getElementById("flash-data");
        if (flashData) {
            flashData.querySelectorAll("div[data-category]").forEach((node) => {
                showToast(node.textContent, node.getAttribute("data-category"));
            });
        }

        // Confirmation dialogs for any element with data-confirm="message"
        document.querySelectorAll("[data-confirm]").forEach((form) => {
            form.addEventListener("submit", (e) => {
                if (!window.confirm(form.getAttribute("data-confirm"))) {
                    e.preventDefault();
                }
            });
        });

        // Password show/hide toggles
        document.querySelectorAll(".password-toggle").forEach((btn) => {
            btn.addEventListener("click", () => {
                const input = document.getElementById(btn.getAttribute("data-target"));
                if (!input) return;
                const isHidden = input.type === "password";
                input.type = isHidden ? "text" : "password";
                btn.innerHTML = isHidden
                    ? '<i class="fa-solid fa-eye-slash"></i>'
                    : '<i class="fa-solid fa-eye"></i>';
            });
        });

        // Simple modal open/close via data attributes
        document.querySelectorAll("[data-open-modal]").forEach((trigger) => {
            trigger.addEventListener("click", () => {
                const modal = document.getElementById(trigger.getAttribute("data-open-modal"));
                if (modal) modal.classList.add("open");
            });
        });
        document.querySelectorAll("[data-close-modal]").forEach((trigger) => {
            trigger.addEventListener("click", () => {
                const modal = trigger.closest(".modal-backdrop");
                if (modal) modal.classList.remove("open");
            });
        });
    });

    window.KrishiMitra = window.KrishiMitra || {};
    window.KrishiMitra.showToast = showToast;
})();
