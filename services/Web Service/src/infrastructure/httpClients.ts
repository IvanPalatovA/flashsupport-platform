import axios, { AxiosInstance } from "axios";

import { Settings } from "./config";

export interface UpstreamClients {
  chatOrchestrator: AxiosInstance;
  ragEngine: AxiosInstance;
  knowledgePipeline: AxiosInstance;
}

export function buildUpstreamClients(settings: Settings): UpstreamClients {
  return {
    chatOrchestrator: axios.create({
      baseURL: settings.chatOrchestratorUrl,
      timeout: settings.requestTimeoutSeconds * 1000,
      headers: {
        "Content-Type": "application/json",
      },
    }),
    ragEngine: axios.create({
      baseURL: settings.ragEngineUrl,
      timeout: settings.requestTimeoutSeconds * 1000,
      headers: {
        "Content-Type": "application/json",
      },
    }),
    knowledgePipeline: axios.create({
      baseURL: settings.knowledgePipelineUrl,
      timeout: settings.requestTimeoutSeconds * 1000,
      headers: {
        "Content-Type": "application/json",
      },
    }),
  };
}
