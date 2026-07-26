// Asset viewing. An asset is a `(commit, path)` reference into the repository,
// never a copied file, so the content is fetched from the serve layer at view
// time (`GET /asset`, `/asset/entries`, `/asset/content`).
//
// Blob assets render inline (image) or as a text preview; tree assets are
// browsable one level at a time via the `path` argument, which is relative to
// the asset's own path. Without a server (static/share mode) only the
// reference is shown — that is the honest answer, since the bytes live in git.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import type { RunClient } from "../api";
import type { AssetTreeEntry, RunAssetPayload } from "../types";

const TEXT_PREVIEW_LIMIT = 40_000;

export function AssetCard({ client, payload }: { client: RunClient; payload: RunAssetPayload }) {
  const [subPath, setSubPath] = useState<string>("");

  const view = useQuery({
    queryKey: ["asset", payload.payload_id],
    queryFn: () => client.getAsset(payload.payload_id),
    enabled: client.live,
    retry: false,
  });

  const reference = (
    <dl className="payload-fields">
      <div>
        <dt>commit</dt>
        <dd>
          <code>{payload.commit.slice(0, 12)}</code>
        </dd>
      </div>
      <div>
        <dt>path</dt>
        <dd>{payload.path || "(repository root)"}</dd>
      </div>
    </dl>
  );

  if (!client.live) {
    return (
      <div className="asset-view">
        {reference}
        <p className="muted">
          Assets are git references. Open this run with <code>arctx web</code> to resolve
          the file from the repository.
        </p>
      </div>
    );
  }

  if (view.isLoading) return <p className="muted">resolving asset…</p>;
  if (view.error) {
    return (
      <div className="asset-view">
        {reference}
        <p className="error">{(view.error as Error).message}</p>
      </div>
    );
  }

  const resolution = view.data?.resolution;
  if (!resolution || resolution.status !== "ok") {
    return (
      <div className="asset-view">
        {reference}
        <p className="error">
          {resolution?.message ?? "asset does not resolve here"}
          {resolution?.status ? ` (${resolution.status})` : ""}
        </p>
        {resolution?.status === "missing_commit" && (
          <p className="muted">
            The commit is not in this clone — fetch it, or push the branch that carries it.
          </p>
        )}
      </div>
    );
  }

  const fullPath = [payload.path, subPath].filter(Boolean).join("/");

  return (
    <div className="asset-view">
      {reference}
      {subPath && (
        <p className="asset-breadcrumb">
          <button type="button" className="asset-crumb" onClick={() => setSubPath("")}>
            ← {payload.path || "root"}
          </button>
          <span className="muted"> / {subPath}</span>
        </p>
      )}
      {resolution.kind === "tree" || subPath ? (
        // A sub-path may be a file or a directory: try the listing, and fall
        // back to file content when git says it is not a tree.
        <AssetTree
          client={client}
          payload={payload}
          subPath={subPath}
          fullPath={fullPath}
          onOpen={setSubPath}
        />
      ) : (
        <AssetContent client={client} payload={payload} subPath="" fullPath={fullPath} />
      )}
    </div>
  );
}

function AssetTree({
  client,
  payload,
  subPath,
  fullPath,
  onOpen,
}: {
  client: RunClient;
  payload: RunAssetPayload;
  subPath: string;
  fullPath: string;
  onOpen: (path: string) => void;
}) {
  const entries = useQuery({
    queryKey: ["asset-entries", payload.payload_id, subPath],
    queryFn: () => client.getAssetEntries(payload.payload_id, subPath || undefined),
    retry: false,
  });
  if (entries.isLoading) return <p className="muted">loading directory…</p>;
  if (entries.error) {
    return <AssetContent client={client} payload={payload} subPath={subPath} fullPath={fullPath} />;
  }
  const list = entries.data?.entries ?? [];
  if (list.length === 0) return <p className="muted">(empty directory)</p>;
  return (
    <ul className="asset-entries">
      {list.map((entry) => (
        <li key={entry.path}>
          <button
            type="button"
            className="asset-entry"
            onClick={() => onOpen(relativeTo(payload.path, entry.path))}
          >
            <span className="asset-entry-kind">{entryIcon(entry)}</span>
            <span className="asset-entry-name">{entry.name}</span>
            {entry.size !== null && <span className="muted">{entry.size} B</span>}
          </button>
        </li>
      ))}
    </ul>
  );
}

function AssetContent({
  client,
  payload,
  subPath,
  fullPath,
}: {
  client: RunClient;
  payload: RunAssetPayload;
  subPath: string;
  fullPath: string;
}) {
  const content = useQuery({
    queryKey: ["asset-content", payload.payload_id, subPath],
    queryFn: () => client.getAssetContent(payload.payload_id, subPath || undefined),
    retry: false,
  });
  if (content.isLoading) return <p className="muted">loading file…</p>;
  if (content.error) return <p className="error">{(content.error as Error).message}</p>;
  const data = content.data;
  if (!data) return null;

  if (data.content_type.startsWith("image/")) {
    const src =
      data.encoding === "base64"
        ? `data:${data.content_type};base64,${data.content}`
        : `data:${data.content_type};utf8,${encodeURIComponent(data.content)}`;
    return (
      <figure className="payload-media">
        <img src={src} alt={payload.title || fullPath} loading="lazy" />
        <figcaption className="muted">{fullPath}</figcaption>
      </figure>
    );
  }

  if (data.encoding === "base64") {
    return (
      <p className="muted">
        binary file · {data.size} bytes · {data.content_type}
      </p>
    );
  }

  const truncated = data.content.length > TEXT_PREVIEW_LIMIT;
  return (
    <>
      <pre className="payload payload-text">
        {truncated ? data.content.slice(0, TEXT_PREVIEW_LIMIT) : data.content}
      </pre>
      {truncated && <p className="muted">preview truncated ({data.size} bytes total)</p>}
    </>
  );
}

function entryIcon(entry: AssetTreeEntry): string {
  if (entry.kind === "tree") return "📁";
  if (entry.kind === "commit") return "⑂";
  return "📄";
}

// Entry paths come back repo-root-relative; the endpoints want them relative to
// the asset's own path.
function relativeTo(assetPath: string, entryPath: string): string {
  if (!assetPath) return entryPath;
  const prefix = `${assetPath.replace(/\/+$/, "")}/`;
  return entryPath.startsWith(prefix) ? entryPath.slice(prefix.length) : entryPath;
}
