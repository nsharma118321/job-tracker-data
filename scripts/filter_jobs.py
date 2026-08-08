import json
import re
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

JOBS_PATH = Path("jobs.json")
OPEN_URL = "https://raw.githubusercontent.com/nsharma118321/Jobs-Applied/main/data/open-jobs.json"
APPLIED_URL = "https://raw.githubusercontent.com/nsharma118321/Jobs-Applied/main/data/applied-jobs.json"


def load_local():
    return json.loads(JOBS_PATH.read_text(encoding="utf-8"))


def load_remote(url):
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        print(f"Warning: could not load {url}: {exc}")
        return {}


def extract_jobs(value):
    found = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item.get("title") and item.get("company"):
                found.append(item)
            else:
                found.extend(extract_jobs(item))
    elif isinstance(value, dict):
        if value.get("title") and value.get("company"):
            found.append(value)
        else:
            for child in value.values():
                if isinstance(child, (dict, list)):
                    found.extend(extract_jobs(child))
    return found


def norm(value):
    value = str(value or "").lower().strip().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def allowed_title(title):
    t = str(title or "").strip()
    return bool(re.match(
        r"^(?:Lead\s+Data\s+Scientist|Data\s+Scientist)(?:\s*(?:[-–—:,(\/]|$).*)?$",
        t,
        flags=re.IGNORECASE,
    ))


def canonical_url(url):
    if not url:
        return ""
    try:
        parts = urlsplit(str(url).strip())
        host = parts.netloc.lower().replace("www.", "")
        path = re.sub(r"/+$", "", parts.path)
        return urlunsplit((parts.scheme.lower() or "https", host, path, "", ""))
    except Exception:
        return str(url).strip().split("?", 1)[0].split("#", 1)[0].rstrip("/")


def linkedin_job_id(job):
    raw_id = str(job.get("id") or "")
    m = re.search(r"(?:linkedin:)?(\d{7,})", raw_id)
    if m:
        return m.group(1)
    for field in ("url", "portalUrl", "aggUrl", "jdUrl", "jobUrl", "applyUrl"):
        m = re.search(r"-(\d{7,})(?:\?|$|/)", str(job.get(field) or ""))
        if m:
            return m.group(1)
    return ""


def identities(job):
    ids, urls, sigs = set(), set(), set()
    jid = linkedin_job_id(job)
    if jid:
        ids.add(jid)
    for field in ("url", "portalUrl", "aggUrl", "jdUrl", "jobUrl", "applyUrl"):
        u = canonical_url(job.get(field))
        if u:
            urls.add(u)
    title, company, location = norm(job.get("title")), norm(job.get("company")), norm(job.get("location"))
    if title and company:
        sigs.add((title, company, location))
        sigs.add((title, company, ""))
    return ids, urls, sigs


def build_seen(jobs):
    seen = (set(), set(), set())
    for job in jobs:
        add_seen(job, seen)
    return seen


def add_seen(job, seen):
    ids, urls, sigs = identities(job)
    seen[0].update(ids)
    seen[1].update(urls)
    seen[2].update(sigs)


def is_seen(job, seen):
    ids, urls, sigs = identities(job)
    return bool(ids & seen[0] or urls & seen[1] or sigs & seen[2])


def main():
    data = load_local()
    incoming = extract_jobs(data)
    existing = extract_jobs(load_remote(OPEN_URL)) + extract_jobs(load_remote(APPLIED_URL))
    existing_seen = build_seen(existing)
    batch_seen = (set(), set(), set())
    kept = []

    for job in incoming:
        if not allowed_title(job.get("title")):
            continue
        if is_seen(job, existing_seen):
            continue
        if is_seen(job, batch_seen):
            continue
        kept.append(job)
        add_seen(job, batch_seen)

    if isinstance(data, dict):
        data["jobs"] = kept
        data["categories"] = [{"key": "ds", "label": "Data Scientist / Lead Data Scientist"}]
        data["source"] = "extension feed filtered for Panda Mami"
        data["filterPolicy"] = "Data Scientist + Lead Data Scientist only; excludes Jobs Applied, Open Roles and batch duplicates"
        output = data
    else:
        output = kept

    JOBS_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Extension feed filtered: {len(incoming)} -> {len(kept)}")


if __name__ == "__main__":
    main()
