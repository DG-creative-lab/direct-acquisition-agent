import React from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";
import "./brand/tokens.css";
import App from "./App";
import "./styles.css";
import "./brand/application.css";
import "./historical-preview.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
