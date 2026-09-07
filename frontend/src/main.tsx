import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { App } from "./App";
import "./index.css";
import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor/editor/editor.api.js";
import "monaco-editor/languages/definitions/python/register.js";
import EditorWorker from "monaco-editor/editor/editor.worker.js?worker";

self.MonacoEnvironment = { getWorker: () => new EditorWorker() };
loader.config({ monaco });

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{ token: { colorPrimary: "#2563eb", borderRadius: 8 } }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>,
);
