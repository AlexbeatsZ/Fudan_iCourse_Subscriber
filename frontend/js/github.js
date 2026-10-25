/**
 * GitHub API client for reading/writing the encrypted database.
 *
 * Read:  raw.githubusercontent.com (binary, no base64 overhead for 57MB file)
 * Write: Git Data API (blobs → tree → commit → update ref) for large files
 */

window.ICS = window.ICS || {};

const _GH_API = "https://api.github.com";

function _ghHeaders(token) {
  return {
    Authorization: `token ${token}`,
    Accept: "application/vnd.github+json",
  };
}

function _detectRepo() {
  const host = location.hostname;
  const path = location.pathname;
  if (host.endsWith(".github.io")) {
    const owner = host.replace(".github.io", "");
    const repo = path.split("/").filter(Boolean)[0];
    if (owner && repo) return { owner, repo };
  }
  return null;
}

async function _getLatestCommitSha(owner, repo, branch, token) {
  const res = await fetch(
    `${_GH_API}/repos/${owner}/${repo}/git/ref/heads/${branch}`,
    { headers: _ghHeaders(token) }
  );
  if (res.status === 404) {
    throw new Error(`Branch '${branch}' not found. Has the workflow run at least once?`);
  }
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`GitHub API error ${res.status}: ${body}`);
  }
  const data = await res.json();
  return data.object.sha;
}

async function _fetchBlobBytes(owner, repo, blobSha, token) {
  const res = await fetch(
    `${_GH_API}/repos/${owner}/${repo}/git/blobs/${blobSha}`,
    {
      headers: {
        Authorization: `token ${token}`,
        Accept: "application/vnd.github.raw",
      },
    }
  );
  if (!res.ok) throw new Error(`Failed to download blob ${blobSha}: ${res.status}`);
  const buffer = await res.arrayBuffer();
  return new Uint8Array(buffer);
}

async function _fetchShardManifest(owner, repo, branch, token) {
  // Walk the data branch tree to find icourse-index.enc + every shard file.
  // Returns:
  //   { commitSha, format: "sharded" | "legacy",
  //     index?: { sha, name },          // sharded only
  //     shards?: [{ name, sha, size }], // sharded only
  //     legacy?: { name, sha, compressed } }  // legacy only
  const commitSha = await _getLatestCommitSha(owner, repo, branch, token);

  const commitRes = await fetch(
    `${_GH_API}/repos/${owner}/${repo}/git/commits/${commitSha}`,
    { headers: _ghHeaders(token) }
  );
  if (!commitRes.ok) throw new Error(`Failed to get commit: ${commitRes.status}`);
  const treeSha = (await commitRes.json()).tree.sha;

  const treeRes = await fetch(
    `${_GH_API}/repos/${owner}/${repo}/git/trees/${treeSha}?recursive=1`,
    { headers: _ghHeaders(token) }
  );
  if (!treeRes.ok) throw new Error(`Failed to get tree: ${treeRes.status}`);
  const tree = (await treeRes.json()).tree;

  const indexEntry = tree.find((e) => e.path === "data/icourse-index.enc");
  if (indexEntry) {
    const shards = tree
      .filter((e) => e.type === "blob" && e.path.startsWith("data/shards/"))
      .map((e) => ({
        name: e.path.slice("data/shards/".length),
        sha: e.sha,
        size: e.size,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
    return {
      commitSha,
      format: "sharded",
      index: { sha: indexEntry.sha, name: "icourse-index.enc" },
      shards,
    };
  }

  // Legacy fallback (single-file format)
  const gz = tree.find((e) => e.path === "data/icourse.db.gz.enc");
  const raw = tree.find((e) => e.path === "data/icourse.db.enc");
  const legacy = gz || raw;
  if (!legacy) throw new Error("Database not found on data branch.");
  return {
    commitSha,
    format: "legacy",
    legacy: {
      name: legacy.path.slice("data/".length),
      sha: legacy.sha,
      compressed: !!gz,
    },
  };
}

/* ── Public subscriptions on the data branch ────────────────────────────
   PAT requires Contents: Read and write only; editing the file uses its
   known blob SHA for GitHub's optimistic-concurrency conflict detection.
*/

function _subscriptionsUrl(owner, repo) {
  return `${_GH_API}/repos/${owner}/${repo}/contents/data/subscriptions.json`;
}

async function _getSubscriptions(owner, repo, token) {
  const res = await fetch(`${_subscriptionsUrl(owner, repo)}?ref=data`, {
    headers: _ghHeaders(token),
  });
  if (res.status === 404) return null; // Old data branch, not yet migrated.
  if (!res.ok) throw new Error(`无法读取订阅列表：GitHub HTTP ${res.status}`);
  const file = await res.json();
  if (file.encoding !== "base64") throw new Error("不支持的订阅配置文件编码");
  const decoded = atob(file.content.replace(/\s/g, ""));
  const config = JSON.parse(decoded);
  if (!Array.isArray(config.course_ids) ||
      !config.course_ids.every((id) => /^\d+$/.test(String(id)))) {
    throw new Error("data/subscriptions.json 格式错误：需要数字 ID 数组");
  }
  return { ids: [...new Set(config.course_ids.map(String))], sha: file.sha };
}

async function _saveSubscriptions(owner, repo, token, courseIds, sha) {
  const ids = [...new Set(courseIds.map(String).map((s) => s.trim()))];
  if (!ids.every((id) => /^\d+$/.test(id))) {
    throw new Error("课程 ID 必须是数字");
  }
  const json = JSON.stringify({ course_ids: ids }, null, 2) + "\n";
  const payload = {
    message: "chore: update course subscriptions",
    branch: "data",
    content: btoa(json), // Numeric IDs and ASCII JSON only.
  };
  if (sha) payload.sha = sha;
  const res = await fetch(_subscriptionsUrl(owner, repo), {
    method: "PUT",
    headers: { ..._ghHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.status === 200 || res.status === 201) {
    return { ids, sha: (await res.json()).content.sha };
  }
  if (res.status === 409 || res.status === 422) {
    throw new Error("订阅已被其他操作更新，或 data 分支还未初始化。请刷新页面后重试。");
  }
  if (res.status === 403) {
    throw new Error("无权保存订阅。GitHub PAT 需要 Contents: Read and write 权限。");
  }
  throw new Error(`无法保存订阅：GitHub HTTP ${res.status}`);
}

async function _triggerSingleRunWorkflow(owner, repo, ref, token, courseIds, useOfficial) {
  const url = `${_GH_API}/repos/${owner}/${repo}/actions/workflows/single_run.yml/dispatches`;
  const ids = (Array.isArray(courseIds) ? courseIds : [])
    .map(String).map((s) => s.trim()).filter(Boolean).join(",");
  if (!ids) throw new Error("单次运行列表为空");
  const inputs = { course_ids: ids };
  if (useOfficial) inputs.use_official_transcript = "true";
  const res = await fetch(url, {
    method: "POST",
    headers: { ..._ghHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify({
      ref: ref || "main",
      inputs: inputs,
    }),
  });
  if (res.status === 204) return;
  const body = await res.text();
  if (res.status === 403 || res.status === 404) {
    throw new Error(
      "无法触发 single_run workflow。请确认 PAT 已开启 Actions: Read and write " +
      `权限，且 single_run.yml 存在于 ref '${ref || "main"}'。服务端返回：${res.status} ${body}`
    );
  }
  if (res.status === 422) {
    throw new Error(
      "触发失败 (422)：通常是 inputs 不匹配 workflow 定义，或 single_run.yml " +
      `不存在于指定分支 '${ref || "main"}'。服务端返回：${body}`
    );
  }
  throw new Error(`GitHub API error ${res.status}: ${body}`);
}

async function _triggerDeleteWorkflow(owner, repo, ref, token, courseIds, subIds) {
  const url = `${_GH_API}/repos/${owner}/${repo}/actions/workflows/delete_course.yml/dispatches`;
  const ids = (Array.isArray(courseIds) ? courseIds : [])
    .map(String).map((s) => s.trim()).filter(Boolean).join(",");
  if (!ids) throw new Error("删除列表为空");
  var inputs = { course_ids: ids };
  if (subIds && subIds.length) {
    inputs.sub_ids = (Array.isArray(subIds) ? subIds : [])
      .map(String).map((s) => s.trim()).filter(Boolean).join(",");
  }
  const res = await fetch(url, {
    method: "POST",
    headers: { ..._ghHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify({
      ref: ref || "main",
      inputs: inputs,
    }),
  });
  if (res.status === 204) return;
  const body = await res.text();
  if (res.status === 403 || res.status === 404) {
    throw new Error(
      "无法触发删除 workflow。请确认你的 GitHub PAT 已开启 " +
      "Actions: Read and write 权限。" +
      `服务端返回：${res.status} ${body}`
    );
  }
  throw new Error(`GitHub API error ${res.status}: ${body}`);
}

async function _triggerExportWorkflow(
  owner, repo, ref, token, courseId, exportType, subIds
) {
  // Fires the existing .github/workflows/export.yml workflow_dispatch.
  // The workflow runs scripts/export_course.py (WeasyPrint) and emails
  // the resulting PDF to RECEIVER_EMAIL — same output the user gets when
  // triggering the workflow manually from the Actions UI.
  //
  // Requires the PAT to grant Actions: Write (in addition to Contents:RW).
  const url = `${_GH_API}/repos/${owner}/${repo}/actions/workflows/export.yml/dispatches`;
  const payload = {
    ref,
    inputs: {
      course_id: String(courseId),
      export_type: exportType || "PDF",
      sub_ids: subIds || "",
    },
  };
  const res = await fetch(url, {
    method: "POST",
    headers: { ..._ghHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.status === 204) return; // success — workflow_dispatch returns 204 No Content
  const body = await res.text();
  if (res.status === 403 || res.status === 404) {
    throw new Error(
      "无法触发导出 workflow。请确认你的 GitHub PAT 已开启 " +
      "Actions: Read and write 权限（Contents 权限不足以触发 workflow）。" +
      `服务端返回：${res.status} ${body}`
    );
  }
  if (res.status === 422) {
    throw new Error(
      "触发失败 (422)：通常是 inputs 不匹配 workflow 定义，或 export.yml " +
      `不存在于指定分支 '${ref}'。服务端返回：${body}`
    );
  }
  throw new Error(`GitHub API error ${res.status}: ${body}`);
}

window.ICS.github = {
  detectRepo: _detectRepo,
  getLatestCommitSha: _getLatestCommitSha,
  fetchBlobBytes: _fetchBlobBytes,
  fetchShardManifest: _fetchShardManifest,
  triggerExportWorkflow: _triggerExportWorkflow,
  triggerDeleteWorkflow: _triggerDeleteWorkflow,
  triggerSingleRunWorkflow: _triggerSingleRunWorkflow,
  getSubscriptions: _getSubscriptions,
  saveSubscriptions: _saveSubscriptions,
};
