import { read, token } from "./api";

export type OutcomeOperation = "register" | "import" | "finalize";
export type OutcomePending = {
  store_id: string;
  operation: OutcomeOperation;
  payload: Record<string, unknown> & { request_id: string };
  company_name: string;
  company_id: string;
};
export type OutcomeEnvelope = {
  store_id: string;
  operation: OutcomeOperation;
  request_id: string;
  result: Record<string, unknown> & { cohort_id: string };
};

// One atomic browser recovery slot. Uploaded source text can exceed sessionStorage.
// Never persist workspace tokens or provider credentials here.
export function outcomePending(
  change?: (saved: OutcomePending | null) => OutcomePending | null,
): Promise<OutcomePending | null> {
  return new Promise((resolve, reject) => {
    const opening = indexedDB.open("workspace-recorded-outcomes", 1);
    opening.onupgradeneeded = () => opening.result.createObjectStore("pending");
    opening.onerror = () =>
      reject(
        new Error(
          "Browser recovery storage is unavailable. No upload was sent.",
        ),
      );
    opening.onblocked = () =>
      reject(new Error("Close other workspace tabs to open recovery storage."));
    opening.onsuccess = () => {
      const db = opening.result;
      const transaction = db.transaction(
        "pending",
        change ? "readwrite" : "readonly",
      );
      const store = transaction.objectStore("pending");
      const request = store.get("original");
      let value: OutcomePending | null = null;
      let failure: unknown;
      request.onsuccess = () => {
        try {
          const saved = (request.result as OutcomePending | undefined) ?? null;
          value = change ? change(saved) : saved;
          if (change) {
            if (value) store.put(value, "original");
            else store.delete("original");
          }
        } catch (error) {
          failure = error;
          transaction.abort();
        }
      };
      transaction.oncomplete = () => {
        db.close();
        resolve(value);
      };
      transaction.onabort = () => {
        db.close();
        reject(
          failure ??
            new Error(
              "Could not retain the original upload. No new upload was sent.",
            ),
        );
      };
    };
  });
}

export async function outcomeStore() {
  return (await read<{ store_id: string }>("/api/outcomes/store")).store_id;
}
export async function outcomePreview<T>(
  store: string,
  operation: OutcomeOperation,
  payload: Record<string, unknown>,
): Promise<T> {
  const response = await fetch(`/api/outcomes/${operation}-preview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Workspace-Token": token(),
      "X-Outcomes-Store": store,
    },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(result.error ?? "Could not preview recorded evidence.");
  if (result.store_id !== store)
    throw new Error("The workspace store changed. Review the source again.");
  return result;
}
export async function saveOutcomeIntent(
  intent: Omit<OutcomePending, "payload"> & {
    payload: Record<string, unknown>;
  },
) {
  const next: OutcomePending = {
    ...intent,
    payload: { ...intent.payload, request_id: crypto.randomUUID() },
  };
  const saved = await outcomePending((old) => {
    if (old)
      throw new Error(
        "Recover the original upload before submitting another request.",
      );
    return next;
  });
  if (!saved) throw new Error("Could not retain the original upload.");
  return saved;
}
export async function dispatchOutcome(
  pending: OutcomePending,
): Promise<OutcomeEnvelope> {
  if ((await outcomeStore()) !== pending.store_id)
    throw new Error(
      "This pending request belongs to a different workspace store. Restore the original store before retrying. The request has been kept.",
    );
  // Check that another tab has not replaced the recovery slot before dispatch.
  const saved = await outcomePending();
  if (JSON.stringify(saved) !== JSON.stringify(pending))
    throw new Error(
      "The recovery record changed in another tab. Reload before continuing.",
    );
  const response = await fetch(`/api/outcomes/${pending.operation}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Workspace-Token": token(),
      "X-Outcomes-Store": pending.store_id,
    },
    body: JSON.stringify(pending.payload),
  });
  const result = await response.json();
  const bound =
    result.store_id === pending.store_id &&
    result.request_id === pending.payload.request_id &&
    result.operation === pending.operation;
  if (bound && (response.ok || result.outcomes_not_saved === true)) {
    if (
      response.ok &&
      (!result.result?.cohort_id ||
        (pending.payload.cohort_id &&
          result.result.cohort_id !== pending.payload.cohort_id))
    )
      throw new Error(
        "The reply did not match the original cohort. Recovery has been kept.",
      );
    await outcomePending((current) =>
      current?.payload.request_id === pending.payload.request_id
        ? null
        : current,
    );
  }
  if (!response.ok || !bound)
    throw new Error(
      result.error ??
        "The reply is uncertain. Recover the original request before continuing.",
    );
  return result;
}
