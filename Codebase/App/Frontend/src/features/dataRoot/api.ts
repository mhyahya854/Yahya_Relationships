import { api } from "../../api";
import type { DataRootHealth, DataRootStatus } from "./types";

export const dataRootApi = {
  getStatus: () => api.dataRoot.status(),
  validate: () => api.dataRoot.validate(),
  inspect: (rootPath: string) => api.dataRoot.inspect(rootPath),
  inspectBackup: (backupPath: string) => api.dataRoot.inspectBackup(backupPath),
  repair: () => api.dataRoot.repair(),
  move: (destinationPath: string) => api.dataRoot.move(destinationPath),
  switch: (rootPath: string) => api.dataRoot.switch(rootPath),
  initialize: (targetPath: string, ownerName: string, ownerGender?: string) => api.dataRoot.initialize(targetPath, ownerName, ownerGender),
  restoreTo: (backupPath: string, targetPath: string) => api.dataRoot.restoreTo(backupPath, targetPath),
};
