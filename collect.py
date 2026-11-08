"""Gather the latest integration reports of nipreps/mriqc into a static site.

For master and for each open pull request, take the most recent finished run of the
Integration workflow, download its amd64 report artifacts, and write index pages.
The site serves the reports' HTML on nipreps.org, so a pull request is included only
if its author is a member or collaborator of nipreps/mriqc, or a maintainer has added
the ``ci-reports`` label. Exits early, writing nothing, if the runs are the same as in
the deployed site's ``manifest.json``.
"""

import argparse
import html
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = 'nipreps/mriqc'
WORKFLOW = 'integration.yml'
LABEL = 'ci-reports'
TRUSTED = {'OWNER', 'MEMBER', 'COLLABORATOR'}
# Cancelled runs (superseded by a newer push) may have no reports
FINISHED = {'success', 'failure'}
MAX_BYTES = 900 * 1024**2
# Artifact ``reports-<dataset>-amd64`` holds ``group_<modality>.html``
MODALITIES = {'dwi': 'dwi', 'flair': 'FLAIR'}
ATTRIBUTION = (
    'DWI reports show data from the Healthy Brain Network (Alexander et al., 2017, '
    'Sci Data 4:170181; CC BY 4.0). FLAIR reports show data from OpenNeuro ds007486 (CC0).'
)
STYLE = (
    'body{font-family:sans-serif;margin:2em;max-width:70em}'
    'td,th{padding:.3em .8em;text-align:left;vertical-align:top}'
)


def gh_api(path):
    out = subprocess.run(['gh', 'api', '-X', 'GET', path], check=True, capture_output=True)
    return json.loads(out.stdout)


def finished_runs(**params):
    """Finished Integration runs, newest first."""
    query = '&'.join(
        f'{k}={v}' for k, v in {'status': 'completed', 'per_page': 100, **params}.items()
    )
    runs = gh_api(f'repos/{REPO}/actions/workflows/{WORKFLOW}/runs?{query}')['workflow_runs']
    return [r for r in runs if r['conclusion'] in FINISHED]


def pr_run(pr, runs):
    """The run of the PR's head commit, else the PR branch's latest (a newer one is running)."""
    head = pr['head']
    for run in runs:
        if run['head_sha'] == head['sha']:
            return run
    if head['repo'] is None:
        return None
    for run in runs:
        if (run['head_repository'] or {}).get('full_name') == head['repo']['full_name'] and (
            run['head_branch'] == head['ref']
        ):
            return run
    return None


def wanted_refs():
    """Master first, then open PRs by most recent update."""
    refs = []
    if master := finished_runs(branch='master', event='push'):
        refs.append({'name': 'master', 'title': 'master', 'url': None, 'run': master[0]})
    pr_runs = finished_runs(event='pull_request')
    pulls = gh_api(f'repos/{REPO}/pulls?state=open&sort=updated&direction=desc&per_page=100')
    for pr in pulls:
        labels = {label['name'] for label in pr['labels']}
        if pr['author_association'] not in TRUSTED and LABEL not in labels:
            continue
        if run := pr_run(pr, pr_runs):
            refs.append(
                {
                    'name': f'pr-{pr["number"]}',
                    'title': f'#{pr["number"]} {pr["title"]}',
                    'url': pr['html_url'],
                    'run': run,
                }
            )
    return refs


def deployed_manifest(site_url):
    try:
        with urllib.request.urlopen(f'{site_url}/manifest.json', timeout=30) as resp:
            return json.load(resp)
    except (OSError, ValueError):
        return None


def download(run_id, dest):
    """Download the run's amd64 reports into ``dest/<artifact>/``; return their size."""
    subprocess.run(
        [
            'gh',
            'run',
            'download',
            str(run_id),
            '-R',
            REPO,
            '-p',
            'reports-*-amd64',
            '-D',
            str(dest),
        ],
        check=False,
    )
    return sum(f.stat().st_size for f in dest.rglob('*') if f.is_file()) if dest.exists() else 0


def datasets(dest):
    """``(modality, artifact directory)`` pairs, in a stable order."""
    pairs = []
    for d in sorted(p for p in dest.iterdir() if p.is_dir()):
        parts = d.name.split('-')
        if len(parts) == 3 and parts[1] in MODALITIES:
            pairs.append((MODALITIES[parts[1]], d))
    return pairs


def page(title, body):
    return (
        f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{html.escape(title)}</title><style>{STYLE}</style></head><body>\n'
        f'{body}\n<p><small>{html.escape(ATTRIBUTION)}</small></p>\n</body></html>\n'
    )


def run_line(ref):
    run = ref['run']
    title = html.escape(ref['title'])
    if ref['url']:
        title = f'<a href="{ref["url"]}">{title}</a>'
    return (
        f'{title}: <code>{run["head_sha"][:7]}</code>, '
        f'{run["updated_at"][:16].replace("T", " ")} UTC, '
        f'<a href="{run["html_url"]}">run {run["conclusion"]}</a>'
    )


def ref_page(ref, dest):
    """One section per dataset: the group report, then the participant reports."""
    sections = []
    for modality, d in datasets(dest):
        group = f'group_{modality}.html'
        items = ''.join(
            f'<li><a href="{d.name}/{f.name}">{html.escape(f.stem)}</a></li>'
            for f in sorted(d.glob('*.html'))
            if f.name != group
        )
        sections.append(
            f'<h2>{modality}</h2><p><a href="{d.name}/{group}">Group report</a></p><ul>{items}</ul>'
        )
    return page(
        f'MRIQC integration reports: {ref["name"]}',
        f'<p><a href="../">All refs</a></p><h1>{html.escape(ref["name"])}</h1>'
        f'<p>{run_line(ref)}</p>{"".join(sections)}',
    )


def index_page(entries):
    rows = []
    for ref, dest in entries:
        links = ' · '.join(
            f'<a href="{ref["name"]}/{d.name}/group_{modality}.html">{modality}</a>'
            for modality, d in datasets(dest)
        )
        rows.append(
            f'<tr><td><a href="{ref["name"]}/">{html.escape(ref["name"])}</a></td>'
            f'<td>{run_line(ref)}</td><td>{links}</td></tr>'
        )
    return page(
        'MRIQC integration reports',
        f'<h1>MRIQC integration reports</h1>\n<p>The latest run of '
        f'<a href="https://github.com/{REPO}/actions/workflows/{WORKFLOW}">Integration</a> '
        f'for master and each open pull request (amd64). Pull requests by members and '
        f'collaborators are listed; others need the <code>{LABEL}</code> label.</p>\n'
        f'<table><tr><th>Ref</th><th>Run</th><th>Group reports</th></tr>\n'
        f'{"".join(rows)}\n</table>',
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('out_dir')
    parser.add_argument('--site-url', default='https://www.nipreps.org/mriqc-ci-reports')
    parser.add_argument('--force', action='store_true', help='rebuild even if nothing changed')
    opts = parser.parse_args()

    refs = wanted_refs()
    manifest = {r['name']: r['run']['id'] for r in refs}
    changed = opts.force or deployed_manifest(opts.site_url) != manifest
    if outputs := os.getenv('GITHUB_OUTPUT'):
        with open(outputs, 'a') as f:
            f.write(f'changed={str(changed).lower()}\n')
    if not changed:
        print('Nothing changed since the last deployment.')
        return

    site = Path(opts.out_dir)
    site.mkdir(parents=True, exist_ok=True)
    total, entries = 0, []
    for ref in refs:
        dest = site / ref['name']
        size = download(ref['run']['id'], dest)
        if not size or total + size > MAX_BYTES:
            shutil.rmtree(dest, ignore_errors=True)
            reason = 'no reports' if not size else f'the site would exceed {MAX_BYTES >> 20} MB'
            # Kept in the manifest, so that expired artifacts do not trigger rebuilds
            print(f'Skipping {ref["name"]}: {reason}', file=sys.stderr)
            continue
        total += size
        (dest / 'index.html').write_text(ref_page(ref, dest))
        entries.append((ref, dest))
    (site / 'index.html').write_text(index_page(entries))
    (site / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Site: {len(entries)} refs, {total >> 20} MB')


if __name__ == '__main__':
    main()
