import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// 开发时 /api 与评测页的图 /reports 代理到 src/huayan/ui/server.py
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { "/api": "http://127.0.0.1:8766", "/reports": "http://127.0.0.1:8766" },
    watch: { usePolling: !!process.env.WSL_DISTRO_NAME },   // WSL 里跑 /mnt/d 上的仓库收不到文件变更事件，改为轮询
  },
});
