"""Check every configured competitor page for changes since last run.

    python run.py                 # check + print, no posting
    python run.py --post          # also post any changes to Slack

Run this daily or weekly via whatever scheduler you're already using for the
Buy Policy reports — the script itself doesn't know or care which cadence
it's on, it just checks everything each time it's invoked.
"""

import argparse
import time
from datetime import datetime, timezone

import diff
import store
from config import REQUEST_DELAY_SECONDS, SLACK_CHANNEL, TARGETS
from fetcher import fetch_text


def check_target(target: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    label = f"{target['company']} — {target['label']}"
    try:
        text = fetch_text(target["url"])
    except Exception as exc:
        return {"label": label, "status": "error", "detail": str(exc)}

    prior = store.get(target["url"])
    new_hash = store.text_hash(text)

    if prior is None:
        store.put(target["url"], text, checked_at=now)
        return {"label": label, "status": "baseline"}

    if prior["hash"] == new_hash:
        store.put(target["url"], text, checked_at=now, changed_at=prior["last_changed"])
        return {"label": label, "status": "unchanged"}

    changes = diff.summarize(prior["text"], text)
    store.put(target["url"], text, checked_at=now, changed_at=now)
    return {"label": label, "url": target["url"], "status": "changed", "changes": changes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--post", action="store_true", help="Post any detected changes to Slack.")
    args = parser.parse_args()

    results = []
    for i, target in enumerate(TARGETS):
        results.append(check_target(target))
        if i < len(TARGETS) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    changed = [r for r in results if r["status"] == "changed"]
    baselined = [r for r in results if r["status"] == "baseline"]
    errored = [r for r in results if r["status"] == "error"]

    print(f"Checked {len(results)} pages — {len(changed)} changed, "
          f"{len(baselined)} new baseline, {len(errored)} errors, "
          f"{len(results) - len(changed) - len(baselined) - len(errored)} unchanged.\n")

    for r in errored:
        print(f"⚠️  {r['label']}: fetch failed — {r['detail']}")

    for r in baselined:
        print(f"🆕 {r['label']}: no prior snapshot — recorded as baseline.")

    lines_for_slack = []
    for r in changed:
        print(f"🔔 {r['label']} changed ({r['url']}):")
        for line in r["changes"]:
            print(f"    {line}")
        lines_for_slack.append(f"*{r['label']}*\n" + "\n".join(f"`{l}`" for l in r["changes"][:8]))

    if args.post and changed:
        from slack_sdk import WebClient
        import os

        client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        message = "🔎 *Competitor watch — changes detected*\n\n" + "\n\n".join(lines_for_slack)
        client.chat_postMessage(channel=SLACK_CHANNEL, text=message)
        print("\n[posted to Slack]")
    elif args.post:
        print("\n[no changes — nothing posted]")


if __name__ == "__main__":
    main()
