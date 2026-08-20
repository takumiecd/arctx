import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { App } from "./App";
import { installGlobalPayloadExtensionApi } from "./payloadExtensions";
import "./index.css";
import "./overview.css";
import "./trials.css";
import "./topics.css";

const queryClient = new QueryClient();
installGlobalPayloadExtensionApi();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
