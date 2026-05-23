import React from "react";
import { createRoot } from "react-dom/client";
import { AppV1 } from "./AppV1.jsx";
import { AppV2 } from "./AppV2.jsx";
import "./styles.css";

const params = new URLSearchParams(window.location.search);
const useV1 = params.get("v") === "1";
const App = useV1 ? AppV1 : AppV2;

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
