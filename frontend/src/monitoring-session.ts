export type MonitoringIntent = {
  path: string;
  requestId: string;
  payload: Record<string, unknown>;
};

function pendingKey(session: string, cohort: string) {
  return JSON.stringify([session, cohort]);
}

function pendingRecord(
  key: string,
  change?: (current: MonitoringIntent | null) => MonitoringIntent | null,
): Promise<MonitoringIntent | null> {
  return new Promise((resolve, reject) => {
    const opening = indexedDB.open("workspace-monitoring", 1);
    opening.onupgradeneeded = () => {
      opening.result.createObjectStore("pending");
    };
    opening.onerror = () =>
      reject(
        new Error("Pending report uploads could not be saved in this browser."),
      );
    opening.onblocked = () =>
      reject(
        new Error("Close other workspace tabs and retry saving this upload."),
      );
    opening.onsuccess = () => {
      const database = opening.result;
      let transaction: IDBTransaction;
      try {
        transaction = database.transaction(
          "pending",
          change ? "readwrite" : "readonly",
        );
      } catch {
        database.close();
        reject(
          new Error(
            "Pending report uploads could not be loaded. Reload the workspace and retry.",
          ),
        );
        return;
      }
      const store = transaction.objectStore("pending");
      const request = store.get(key);
      let result: MonitoringIntent | null = null;
      let failure: unknown;
      request.onsuccess = () => {
        try {
          const current =
            (request.result as MonitoringIntent | undefined) ?? null;
          result = change ? change(current) : current;
          if (change) {
            if (result) store.put(result, key);
            else store.delete(key);
          }
        } catch (error) {
          failure = error;
          transaction.abort();
        }
      };
      transaction.oncomplete = () => {
        database.close();
        resolve(result);
      };
      transaction.onabort = () => {
        database.close();
        reject(
          failure ??
            new Error(
              "Pending report uploads could not be saved in this browser.",
            ),
        );
      };
    };
  });
}

export function pendingMonitoring(session: string, cohort: string) {
  return pendingRecord(pendingKey(session, cohort));
}

export async function monitoringCommand<T>(
  path: string,
  payload: Record<string, unknown>,
  workspaceToken: string,
): Promise<T> {
  const session = /^\/api\/sessions\/([^/]+)\/monitoring-(start|update)$/.exec(
    path,
  )?.[1];
  if (!session || typeof payload.cohort_id !== "string")
    throw new Error("Select the campaign and cohort for monitoring.");
  const key = pendingKey(session, payload.cohort_id);
  const pending = await pendingRecord(key, (saved) => {
    if (saved) {
      if (
        saved.path !== path ||
        JSON.stringify(saved.payload) !== JSON.stringify(payload)
      )
        throw new Error(
          "Recover the saved monitoring request before changing this schedule.",
        );
      return saved;
    }
    return { path, payload, requestId: crypto.randomUUID() };
  });
  if (!pending) throw new Error("The monitoring request could not be saved.");
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Workspace-Token": workspaceToken,
    },
    body: JSON.stringify({ ...pending.payload, request_id: pending.requestId }),
  });
  const result = await response.json();
  if (response.ok || result.monitoring_not_saved === true) {
    await pendingRecord(key, (current) =>
      current?.requestId === pending.requestId ? null : current,
    );
  }
  if (!response.ok)
    throw new Error(
      result.error ?? "The monitoring request could not be confirmed.",
    );
  return result as T;
}
