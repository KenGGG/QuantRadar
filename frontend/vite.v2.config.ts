import {defineConfig} from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({plugins:[react()],server:{host:"127.0.0.1",port:5174,strictPort:true,open:"/v2.html",proxy:{"/api/v2":{target:"http://127.0.0.1:7242"}}},build:{outDir:"dist-v2",emptyOutDir:true,rollupOptions:{input:"v2.html"}}});
