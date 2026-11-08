# MRIQC integration reports

The latest reports of [nipreps/mriqc](https://github.com/nipreps/mriqc)'s
[Integration](https://github.com/nipreps/mriqc/actions/workflows/integration.yml) workflow,
served at <https://www.nipreps.org/mriqc-ci-reports/>.

## How it works

- `.github/workflows/deploy.yml` runs every 15 minutes, on pushes to `main`, and on demand.
- `collect.py` takes the most recent successful Integration run for `master` and for each
  open pull request, downloads its `reports-*-amd64` artifacts, and writes an index page.
  - It exits early when the runs match the deployed `manifest.json`.
  - Pull requests by members and collaborators of nipreps/mriqc are listed. For anyone
    else, a maintainer adds the `ci-reports` label, because the reports' HTML is served
    on nipreps.org.
  - The site is capped at 900 MB (GitHub Pages allows 1 GB). Reports drop out when their
    artifacts expire, after 14 days.
- The site is deployed as a Pages artifact, so nothing is committed and the repository
  does not grow.

Run it locally with an authenticated `gh`:

```bash
python3 collect.py site --force
```

## Settings

- Pages: source "GitHub Actions".
- `MRIQC_READ_TOKEN` (optional secret): a token with Actions read access on nipreps/mriqc,
  used instead of the workflow's own token.

## Data

The reports are derived from public data:

- DWI: the Healthy Brain Network (Alexander et al., 2017, *Sci Data* 4:170181,
  doi:[10.1038/sdata.2017.181](https://doi.org/10.1038/sdata.2017.181)), CC BY 4.0.
- FLAIR: OpenNeuro [ds007486](https://openneuro.org/datasets/ds007486), CC0.
