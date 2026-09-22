/* KrishiMitra — client-side validation for auth forms (server-side
   validation in routes/auth.py remains authoritative). */

(function () {
    function setError(field, message) {
        const errorEl = field.closest(".field").querySelector(".field-error");
        if (errorEl) errorEl.textContent = message || "";
        field.style.borderColor = message ? "#B3402A" : "";
    }

    document.addEventListener("DOMContentLoaded", () => {
        const registerForm = document.getElementById("register-form");
        if (registerForm) {
            const password = document.getElementById("password");
            const confirm = document.getElementById("confirm_password");
            const email = document.getElementById("email");
            const phone = document.getElementById("phone");

            registerForm.addEventListener("submit", (e) => {
                let valid = true;

                if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.value.trim())) {
                    setError(email, "Enter a valid email address.");
                    valid = false;
                } else if (email) setError(email, "");

                if (phone && !/^[6-9]\d{9}$/.test(phone.value.trim())) {
                    setError(phone, "Enter a valid 10-digit mobile number.");
                    valid = false;
                } else if (phone) setError(phone, "");

                if (password && password.value.length < 8) {
                    setError(password, "Password must be at least 8 characters.");
                    valid = false;
                } else if (password) setError(password, "");

                if (confirm && confirm.value !== password.value) {
                    setError(confirm, "Passwords do not match.");
                    valid = false;
                } else if (confirm) setError(confirm, "");

                if (!valid) e.preventDefault();
            });

            if (password && confirm) {
                const checkMatch = () => setError(confirm, confirm.value && confirm.value !== password.value ? "Passwords do not match." : "");
                password.addEventListener("input", checkMatch);
                confirm.addEventListener("input", checkMatch);
            }
        }
    });
})();
