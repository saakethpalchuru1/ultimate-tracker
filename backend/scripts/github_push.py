"""
Minimal helper that pushes a set of files to a GitHub repository using the
Contents API. Designed for the Render cron path -- single HTTP call per
file, no git CLI required.

Required env vars:
  GITHUB_TOKEN   -- fine-grained PAT with Contents: read/write on the repo
  GITHUB_REPO    -- e.g. "saaketh/ultimate-tracker"
  GITHUB_BRANCH  -- optional, defaults to "main"
"""
from __future__ import annotations

import base64
import json
import logging
import os
from typing import Mapping

import httpx

log = logging.getLogger(__name__)


def push_files(files: Mapping[str, str], commit_message: str) -> None:
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPO"]
    branch = os.environ.get("GITHUB_BRANCH", "main")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(headers=headers, timeout=30) as client:
        for path, content in files.items():
            # 1. Get the current SHA (Contents API requires it for updates)
            get_url = f"https://api.github.com/repos/{repo}/contents/{path}"
            r = client.get(get_url, params={"ref": branch})
            sha = r.json()["sha"] if r.status_code == 200 else None

            # 2. Skip if content unchanged (saves a commit per cron tick)
            if r.status_code == 200:
                existing_b64 = r.json().get("content", "").replace("\n", "")
                try:
                    existing = base64.b64decode(existing_b64).decode("utf-8")
                    if existing == content:
                        log.info("%s: unchanged, skipping", path)
                        continue
                except Exception:
                    pass

            body = {
                "message": commit_message,
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "branch": branch,
            }
            if sha:
                body["sha"] = sha

            r = client.put(get_url, json=body)
            r.raise_for_status()
            log.info("%s: %s", path, "updated" if sha else "created")
