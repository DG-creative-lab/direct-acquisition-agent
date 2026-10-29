import { useEffect, useState } from "react";
import { read } from "./api";
import "./knowledge.css";

type Knowledge = {
  playbooks: {
    version: string;
    purpose: string;
    experiment: string;
    playbooks: { id: string; title: string; guidance: string }[];
  };
  product_facts: {
    version: string;
    product: string;
    checked_on: string;
    review_by: string;
    sources: { id: string; title: string; url: string }[];
    facts: {
      id: string;
      copy: string;
      qualification: string;
      source_id: string;
    }[];
  };
  editorial: {
    version: string;
    rules: string[];
    situations: Record<string, string>;
  };
  learning: string;
};

export default function KnowledgeView() {
  const [data, setData] = useState<Knowledge | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    read<Knowledge>("/api/knowledge", controller.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, []);
  return (
    <section className="knowledge-page" aria-labelledby="knowledge-title">
      <div className="knowledge-heading">
        <span className="eyebrow">LOCAL KNOWLEDGE</span>
        <h1 id="knowledge-title">Campaign knowledge</h1>
        <p>Sources and guidance used across the synthetic campaign workflow.</p>
      </div>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p role="status">Loading knowledge...</p>}
      {data && (
        <div className="knowledge-sections">
          <section>
            <div className="knowledge-label">
              01 / PLANNING <span>{data.playbooks.version}</span>
            </div>
            <h2>Campaign playbooks</h2>
            <p>{data.playbooks.purpose}</p>
            {data.playbooks.playbooks.map((p) => (
              <div className="knowledge-row" key={p.id}>
                <div>
                  <strong>{p.title}</strong>
                  <small>{p.id}</small>
                </div>
                <p>{p.guidance}</p>
              </div>
            ))}
            <p>{data.playbooks.experiment}</p>
            <p className="knowledge-note">
              Planning uses a frozen snapshot of these playbooks. Guidance is
              advisory and does not approve a campaign.
            </p>
          </section>
          <section>
            <div className="knowledge-label">
              02 / EVIDENCE <span>{data.product_facts.version}</span>
            </div>
            <h2>{data.product_facts.product}</h2>
            <p>
              Baseline pack checked {data.product_facts.checked_on}. Review by{" "}
              {data.product_facts.review_by}. Campaign review checks its own
              current evidence and freshness.
            </p>
            {data.product_facts.facts.map((f) => (
              <div className="knowledge-row" key={f.id}>
                <div>
                  <strong>{f.id}</strong>
                  <small>Source: {f.source_id}</small>
                </div>
                <p>
                  {f.copy} {f.qualification}
                </p>
              </div>
            ))}
            {data.product_facts.sources.map((s) => (
              <p key={s.id}>
                <a href={s.url} target="_blank" rel="noreferrer">
                  {s.title}
                </a>
              </p>
            ))}
            <p className="knowledge-note">
              Product facts are used for grounded copy and review. They are not
              part of the planning playbook.
            </p>
          </section>
          <section>
            <div className="knowledge-label">
              03 / COPY <span>{data.editorial.version}</span>
            </div>
            <h2>Editorial guidance</h2>
            <p>
              Baseline rules for new copy. Existing runs retain their frozen
              guidance. Reviewer preferences are examples of taste, not measured
              outcomes.
            </p>
            <ul>
              {data.editorial.rules.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </section>
          <section>
            <div className="knowledge-label">04 / OBSERVATION</div>
            <h2>Outcome memory</h2>
            <p>{data.learning}</p>
            <p className="knowledge-note">
              Memory is never a product fact or approval.
            </p>
          </section>
        </div>
      )}
    </section>
  );
}
