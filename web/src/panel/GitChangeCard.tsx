// git_change viewing. The record carries facts only — a branch and the commit
// hashes — so the subject, file list, diff stat, and patch text are derived
// from the repository at view time (POST /web/ext/git/diff).
//
// A commit that is missing from this clone is a normal outcome (shallow clone,
// never pushed): the server answers `available: false` with a note, and that
// note is what gets shown.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import type { RunClient } from "../api";
import type { RunGitChangePayload } from "../types";

export function GitChangeCard({
  client,
  payload,
}: {
  client: RunClient;
  payload: RunGitChangePayload;
}) {
  const [load, setLoad] = useState(false);
  const diff = useQuery({
    queryKey: ["git-diff", payload.target_id],
    queryFn: () => client.getGitChangeDiff(payload.target_id),
    enabled: load && client.live,
    retry: false,
  });

  if (!client.live) {
    return (
      <p className="muted">
        Diffs are derived from the repository — open this run with <code>arctx web</code>{" "}
        to load them.
      </p>
    );
  }

  if (!load) {
    return (
      <button type="button" className="git-diff-load" onClick={() => setLoad(true)}>
        load diff
      </button>
    );
  }
  if (diff.isLoading) return <p className="muted">deriving diff from git…</p>;
  if (diff.error) return <p className="error">{(diff.error as Error).message}</p>;
  const data = diff.data;
  if (!data) return null;

  if (!data.available || data.note) {
    return <p className="muted">{data.note || "(commit not available locally)"}</p>;
  }

  return (
    <div className="git-diff-view">
      <dl className="payload-fields">
        <div>
          <dt>subject</dt>
          <dd>{data.subject}</dd>
        </div>
        <div>
          <dt>changes</dt>
          <dd>
            +{data.diff_stat.insertions} / -{data.diff_stat.deletions} in{" "}
            {data.diff_stat.files_changed} files
          </dd>
        </div>
      </dl>
      {data.files.length > 0 && (
        <details open>
          <summary>files ({data.files.length})</summary>
          <ul className="git-diff-files">
            {data.files.map((file) => (
              <li key={file}>
                <code>{file}</code>
              </li>
            ))}
          </ul>
        </details>
      )}
      {data.truncated && (
        <p className="muted">diff truncated at {data.byte_count.toLocaleString()} bytes</p>
      )}
      <pre className="payload payload-text payload-diff">{data.diff}</pre>
    </div>
  );
}
