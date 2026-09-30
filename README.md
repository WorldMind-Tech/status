# PreWorld Review status

Public status page for [PreWorld Review](https://review.nice2.io): https://worldmind-tech.github.io/status/

- Every 5 minutes, [`check.yml`](.github/workflows/check.yml) runs [`status.py`](status.py), which requests
  `https://review.nice2.io/healthz` and `https://review.nice2.io/docs/` (three tries, 10 s apart) and writes the result to
  [`data/status.json`](data/status.json): the current state, per-day counts for 90 days, the last 50 incidents.
- A check counts as down after two failing rounds in a row. Then an issue labelled `incident` is opened; it is closed when the
  check passes again.
- The page ([`index.html`](index.html)) reads `data/status.json` when it loads. It is redeployed only when it changes
  ([`pages.yml`](.github/workflows/pages.yml)).

Only the public health endpoint and the docs page are requested: no customer data and no credentials are involved.

平台（`/healthz`）和文档站每 5 分钟检查一次，连续两次没通过算故障并开 issue，恢复后自动关闭。只读公开的健康检查和文档页，不涉及客户数据和任何密钥。
