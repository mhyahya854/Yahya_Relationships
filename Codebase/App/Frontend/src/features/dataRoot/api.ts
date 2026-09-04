import { api } from "../../api";
import type { DataRootHealth, DataRootStatus } from "./types";

export const dataRootApi = {
  getStatus: () => api.dataRoot.status(),
  validate: () => api.dataRoot.validate(),
  repair: () => api.dataRoot.repair(),
  move: (destinationPath: string) => api.dataRoot.move(destinationPath),
  switch: (rootPath: string) => api.dataRoot.switch(rootPath),
};
