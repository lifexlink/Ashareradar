document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function () {
      const path = window.location.pathname || "";

      // 只在支付页防重复提交，不影响登录/注册速度体验
      if (!path.includes("/pay/")) {
        return;
      }

      const btn = form.querySelector("button[type='submit']");
      if (btn) {
        btn.disabled = true;
        btn.innerText = "提交中，请稍候...";
        btn.style.opacity = "0.7";
        btn.style.cursor = "not-allowed";
      }
    });
  });
});
