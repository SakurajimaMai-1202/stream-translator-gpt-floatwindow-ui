// vite.config.ts
import { defineConfig } from "file:///G:/youtube-live-translator/floatwindow/ui2/frontend/node_modules/vite/dist/node/index.js";
import vue from "file:///G:/youtube-live-translator/floatwindow/ui2/frontend/node_modules/@vitejs/plugin-vue/dist/index.mjs";
import { fileURLToPath, URL } from "node:url";
import { resolve } from "path";
var __vite_injected_original_dirname = "G:\\youtube-live-translator\\floatwindow\\ui2\\frontend";
var __vite_injected_original_import_meta_url = "file:///G:/youtube-live-translator/floatwindow/ui2/frontend/vite.config.ts";
var vite_config_default = defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", __vite_injected_original_import_meta_url))
    }
  },
  build: {
    outDir: resolve(__vite_injected_original_dirname, "../backend/static"),
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: void 0
      }
    }
  },
  server: {
    // 移除 host 限制，讓 Vite 自動選擇
    port: 5173,
    strictPort: false,
    // 如果端口被佔用，自動使用下一個可用端口
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true
      }
    }
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCJHOlxcXFx5b3V0dWJlLWxpdmUtdHJhbnNsYXRvclxcXFxmbG9hdHdpbmRvd1xcXFx1aTJcXFxcZnJvbnRlbmRcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfZmlsZW5hbWUgPSBcIkc6XFxcXHlvdXR1YmUtbGl2ZS10cmFuc2xhdG9yXFxcXGZsb2F0d2luZG93XFxcXHVpMlxcXFxmcm9udGVuZFxcXFx2aXRlLmNvbmZpZy50c1wiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9pbXBvcnRfbWV0YV91cmwgPSBcImZpbGU6Ly8vRzoveW91dHViZS1saXZlLXRyYW5zbGF0b3IvZmxvYXR3aW5kb3cvdWkyL2Zyb250ZW5kL3ZpdGUuY29uZmlnLnRzXCI7aW1wb3J0IHsgZGVmaW5lQ29uZmlnIH0gZnJvbSAndml0ZSdcclxuaW1wb3J0IHZ1ZSBmcm9tICdAdml0ZWpzL3BsdWdpbi12dWUnXHJcbmltcG9ydCB7IGZpbGVVUkxUb1BhdGgsIFVSTCB9IGZyb20gJ25vZGU6dXJsJ1xyXG5pbXBvcnQgeyByZXNvbHZlIH0gZnJvbSAncGF0aCdcclxuXHJcbi8vIGh0dHBzOi8vdml0ZWpzLmRldi9jb25maWcvXHJcbmV4cG9ydCBkZWZhdWx0IGRlZmluZUNvbmZpZyh7XHJcbiAgcGx1Z2luczogW3Z1ZSgpXSxcclxuICByZXNvbHZlOiB7XHJcbiAgICBhbGlhczoge1xyXG4gICAgICAnQCc6IGZpbGVVUkxUb1BhdGgobmV3IFVSTCgnLi9zcmMnLCBpbXBvcnQubWV0YS51cmwpKVxyXG4gICAgfVxyXG4gIH0sXHJcbiAgYnVpbGQ6IHtcclxuICAgIG91dERpcjogcmVzb2x2ZShfX2Rpcm5hbWUsICcuLi9iYWNrZW5kL3N0YXRpYycpLFxyXG4gICAgZW1wdHlPdXREaXI6IHRydWUsXHJcbiAgICByb2xsdXBPcHRpb25zOiB7XHJcbiAgICAgIG91dHB1dDoge1xyXG4gICAgICAgIG1hbnVhbENodW5rczogdW5kZWZpbmVkXHJcbiAgICAgIH1cclxuICAgIH1cclxuICB9LFxyXG4gIHNlcnZlcjoge1xyXG4gICAgLy8gXHU3OUZCXHU5NjY0IGhvc3QgXHU5NjUwXHU1MjM2XHVGRjBDXHU4QjkzIFZpdGUgXHU4MUVBXHU1MkQ1XHU5MDc4XHU2NEM3XHJcbiAgICBwb3J0OiA1MTczLFxyXG4gICAgc3RyaWN0UG9ydDogZmFsc2UsICAvLyBcdTU5ODJcdTY3OUNcdTdBRUZcdTUzRTNcdTg4QUJcdTRGNTRcdTc1MjhcdUZGMENcdTgxRUFcdTUyRDVcdTRGN0ZcdTc1MjhcdTRFMEJcdTRFMDBcdTUwMEJcdTUzRUZcdTc1MjhcdTdBRUZcdTUzRTNcclxuICAgIHByb3h5OiB7XHJcbiAgICAgICcvYXBpJzoge1xyXG4gICAgICAgIHRhcmdldDogJ2h0dHA6Ly8xMjcuMC4wLjE6ODAwMCcsXHJcbiAgICAgICAgY2hhbmdlT3JpZ2luOiB0cnVlXHJcbiAgICAgIH1cclxuICAgIH1cclxuICB9XHJcbn0pXHJcbiJdLAogICJtYXBwaW5ncyI6ICI7QUFBcVYsU0FBUyxvQkFBb0I7QUFDbFgsT0FBTyxTQUFTO0FBQ2hCLFNBQVMsZUFBZSxXQUFXO0FBQ25DLFNBQVMsZUFBZTtBQUh4QixJQUFNLG1DQUFtQztBQUE4SyxJQUFNLDJDQUEyQztBQU14USxJQUFPLHNCQUFRLGFBQWE7QUFBQSxFQUMxQixTQUFTLENBQUMsSUFBSSxDQUFDO0FBQUEsRUFDZixTQUFTO0FBQUEsSUFDUCxPQUFPO0FBQUEsTUFDTCxLQUFLLGNBQWMsSUFBSSxJQUFJLFNBQVMsd0NBQWUsQ0FBQztBQUFBLElBQ3REO0FBQUEsRUFDRjtBQUFBLEVBQ0EsT0FBTztBQUFBLElBQ0wsUUFBUSxRQUFRLGtDQUFXLG1CQUFtQjtBQUFBLElBQzlDLGFBQWE7QUFBQSxJQUNiLGVBQWU7QUFBQSxNQUNiLFFBQVE7QUFBQSxRQUNOLGNBQWM7QUFBQSxNQUNoQjtBQUFBLElBQ0Y7QUFBQSxFQUNGO0FBQUEsRUFDQSxRQUFRO0FBQUE7QUFBQSxJQUVOLE1BQU07QUFBQSxJQUNOLFlBQVk7QUFBQTtBQUFBLElBQ1osT0FBTztBQUFBLE1BQ0wsUUFBUTtBQUFBLFFBQ04sUUFBUTtBQUFBLFFBQ1IsY0FBYztBQUFBLE1BQ2hCO0FBQUEsSUFDRjtBQUFBLEVBQ0Y7QUFDRixDQUFDOyIsCiAgIm5hbWVzIjogW10KfQo=
